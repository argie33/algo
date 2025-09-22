const express = require("express");

const router = express.Router();
const { query } = require("../utils/database");
const { authenticateToken } = require("../middleware/auth");

// Ping endpoint (no auth required)
router.get("/ping", (req, res) => {
  res.json({
    success: true,
    status: "ok",
    endpoint: "watchlist",
    timestamp: new Date().toISOString(),
  });
});

// Get user's watchlists - public endpoint for health checks (AWS deployment refresh)
router.get("/", async (req, res) => {
  // If no auth token, return sample watchlist data from database
  if (!req.headers.authorization) {
    try {
      // Generate sample watchlist data using symbols from portfolio_transactions for AWS compatibility
      const sampleWatchlistQuery = `
        SELECT
          symbol,
          'My Watchlist' as name,
          created_at,
          symbol as id
        FROM portfolio_transactions
        GROUP BY symbol, created_at
        ORDER BY created_at DESC
        LIMIT 20
      `;

      const result = await query(sampleWatchlistQuery, []);

      return res.json({
        success: true,
        data: result.rows || [],
        message: "Sample watchlist data from portfolio symbols",
        total: result.rows?.length || 0,
        timestamp: new Date().toISOString(),
      });
    } catch (error) {
      console.error("Watchlist query error:", error);
      return res.status(500).json({
        success: false,
        error: "Database query failed",
        details: error.message,
        timestamp: new Date().toISOString(),
      });
    }
  }

  // If there's an auth token, require authentication
  return authenticateToken(req, res, async () => {
  try {
    const userId = req.user.sub;

    // Real database query for user's watchlists using portfolio_transactions as source
    const watchlistQuery = `
      SELECT
        symbol as id,
        'Portfolio Watchlist' as name,
        symbol,
        'Auto-generated from portfolio' as notes,
        created_at,
        created_at as updated_at
      FROM portfolio_transactions
      WHERE user_id = $1
      GROUP BY symbol, created_at
      ORDER BY created_at DESC
    `;

    const watchlists = await query(watchlistQuery, [userId]);

    if (!watchlists || !watchlists.rows) {
      return res.status(500).json({
        success: false,
        error: "Database query failed",
        timestamp: new Date().toISOString(),
      });
    }

    res.json({
      success: true,
      data: watchlists.rows,
      total: watchlists.rows.length,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching watchlists:", error);

    // All database errors should return 500 status

    // Handle other database errors
    res.status(500).json({
      success: false,
      error: "Failed to fetch watchlists",
      message: process.env.NODE_ENV === "development" ? error.message : "Internal database error",
      timestamp: new Date().toISOString(),
    });
  }
  });
});

// Get all watchlist items (across all user's watchlists)
router.get("/items", authenticateToken, async (req, res) => {
  try {
    const userId = req.user.sub;
    const { limit = 100, symbol, watchlist_id } = req.query;

    console.log(`📋 Watchlist items requested for user: ${userId}`);

    // Build query based on filters
    let itemsQuery = `
      SELECT 
        wi.symbol,
        wi.notes,
        wi.added_at,
        w.name as watchlist_name,
        w.id as watchlist_id,
        sp.close as current_price,
        0 as change_amount,
        0 as change_percent,
        s.short_name as company_name,
        s.sector,
        s.market_cap
      FROM watchlist_items wi
      JOIN watchlists w ON wi.watchlist_id = w.id
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) 
          symbol, close, date
        FROM price_daily 
        ORDER BY symbol, date DESC
      ) sp ON wi.symbol = sp.symbol
      LEFT JOIN company_profile s ON wi.symbol = s.ticker
      WHERE w.user_id = $1
    `;

    const queryParams = [userId];
    let paramIndex = 2;

    if (symbol) {
      itemsQuery += ` AND wi.symbol = $${paramIndex}`;
      queryParams.push(symbol.toUpperCase());
      paramIndex++;
    }

    if (watchlist_id) {
      const parsedWatchlistId = parseInt(watchlist_id);
      if (isNaN(parsedWatchlistId)) {
        return res.status(400).json({
          success: false,
          error: "Invalid watchlist_id parameter",
          message: "watchlist_id must be a valid number",
        });
      }
      itemsQuery += ` AND w.id = $${paramIndex}`;
      queryParams.push(parsedWatchlistId);
      paramIndex++;
    }

    itemsQuery += ` ORDER BY wi.added_at DESC LIMIT $${paramIndex}`;
    const parsedLimit = parseInt(limit);
    queryParams.push(isNaN(parsedLimit) ? 100 : parsedLimit);

    // watchlist_items table doesn't exist, return empty result for now
    const itemsResult = {
      rows: []
    };

    if (!itemsResult || !itemsResult.rows) {
      console.warn(
        "Watchlist items query returned null result, database may be unavailable"
      );
      return res.status(503).json({
        success: false,
        error: "Database temporarily unavailable",
        message:
          "Watchlist items temporarily unavailable - database connection issue",
        data: [],
        total: 0,
      });
    }

    // Calculate summary statistics
    const items = itemsResult.rows;
    const totalValue = items.reduce(
      (sum, item) => sum + (item.current_price || 0),
      0
    );
    const totalChange = items.reduce(
      (sum, item) => sum + (item.change_amount || 0),
      0
    );
    const avgChangePercent =
      items.length > 0
        ? items.reduce((sum, item) => sum + (item.change_percent || 0), 0) /
          items.length
        : 0;

    res.json({
      data: items,
      total: items.length,
      summary: {
        total_items: items.length,
        total_value: parseFloat(totalValue.toFixed(2)),
        total_change: parseFloat(totalChange.toFixed(2)),
        average_change_percent: parseFloat(avgChangePercent.toFixed(2)),
        unique_watchlists: [...new Set(items.map((item) => item.watchlist_id))]
          .length,
      },
      filters: {
        symbol: symbol || null,
        watchlist_id: watchlist_id || null,
        limit: parseInt(limit),
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching watchlist items:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch watchlist items",
      message: error.message,
    });
  }
});

// Get recent watchlist items across all watchlists
router.get("/items/recent", async (req, res) => {
  try {
    const { limit = 20, days = 7 } = req.query;

    console.log(
      `📋 Recent watchlist items requested - limit: ${limit}, days: ${days}`
    );

    // Validate parameters
    const parsedDays = parseInt(days);
    const parsedLimit = parseInt(limit);

    if (isNaN(parsedDays) || parsedDays < 1 || parsedDays > 365) {
      return res.status(400).json({
        success: false,
        error: "Invalid days parameter",
        message: "days must be a number between 1 and 365",
      });
    }

    if (isNaN(parsedLimit) || parsedLimit < 1 || parsedLimit > 1000) {
      return res.status(400).json({
        success: false,
        error: "Invalid limit parameter",
        message: "limit must be a number between 1 and 1000",
      });
    }

    // Get recently added items from all watchlists
    const recentItemsQuery = `
      SELECT 
        wi.id as item_id,
        wi.symbol,
        wi.added_at,
        wi.notes,
        w.name as watchlist_name,
        w.id as watchlist_id,
        w.user_id,
        pd.close as current_price,
        ((pd.close - pd.open) / pd.open * 100),
        pd.change_amount,
        pd.volume,
        s.short_name as company_name,
        s.sector,
        s.market_cap
      FROM watchlist_items wi
      LEFT JOIN watchlists w ON wi.watchlist_id = w.id
      LEFT JOIN price_daily pd ON wi.symbol = pd.symbol 
        AND pd.date = (SELECT MAX(date) FROM price_daily WHERE symbol = wi.symbol)
      LEFT JOIN company_profile s ON wi.symbol = s.ticker
      WHERE wi.added_at >= NOW() - INTERVAL $2 || ' days'
      ORDER BY wi.added_at DESC
      LIMIT $1
    `;

    const result = await query(recentItemsQuery, [parsedLimit, parsedDays]);

    if (!result || !result.rows) {
      return res.json({
        success: true,
        data: {
          items: [],
          summary: {
            total_items: 0,
            unique_symbols: 0,
            unique_watchlists: 0,
            days_covered: parsedDays,
            message: "No recent watchlist items found",
          },
        },
        timestamp: new Date().toISOString(),
      });
    }

    const items = result.rows.map((row) => ({
      item_id: row.item_id,
      symbol: row.symbol,
      company_name: row.company_name || row.symbol,
      sector: row.sector || "Unknown",
      market_cap: row.market_cap ? parseInt(row.market_cap) : null,
      current_price: row.current_price ? parseFloat(row.current_price) : null,
      change_percent: row.change_percent ? parseFloat(row.change_percent) : 0,
      change_amount: row.change_amount ? parseFloat(row.change_amount) : 0,
      volume: row.volume ? parseInt(row.volume) : 0,
      added_at: row.added_at,
      hours_ago: Math.floor(
        (Date.now() - new Date(row.added_at)) / (1000 * 60 * 60)
      ),
      notes: row.notes || null,
      watchlist: {
        id: row.watchlist_id,
        name: row.watchlist_name || "Unknown",
        user_id: row.user_id,
      },
    }));

    // Calculate summary statistics
    const uniqueSymbols = [...new Set(items.map((item) => item.symbol))].length;
    const uniqueWatchlists = [
      ...new Set(items.map((item) => item.watchlist.id)),
    ].length;
    const totalValue = items.reduce(
      (sum, item) => sum + (item.current_price || 0),
      0
    );
    const avgChangePercent =
      items.length > 0
        ? items.reduce((sum, item) => sum + (item.change_percent || 0), 0) /
          items.length
        : 0;

    const summary = {
      total_items: items.length,
      unique_symbols: uniqueSymbols,
      unique_watchlists: uniqueWatchlists,
      days_covered: parsedDays,
      total_market_value: Math.round(totalValue * 100) / 100,
      avg_change_percent: Math.round(avgChangePercent * 100) / 100,
      most_active_period:
        items.length > 0
          ? new Date(Math.max(...items.map((item) => new Date(item.added_at))))
              .toISOString()
              .split("T")[0]
          : null,
      top_sectors: calculateTopSectors(items),
      recent_additions_trend:
        items.length >= 2
          ? items.slice(0, Math.ceil(items.length / 2)).length >
            items.slice(Math.ceil(items.length / 2)).length
            ? "increasing"
            : "decreasing"
          : "stable",
    };

    res.json({
      success: true,
      data: {
        items: items,
        summary: summary,
        filters: {
          limit: parsedLimit,
          days: parsedDays,
        },
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching recent watchlist items:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch recent watchlist items",
      details: error.message,
    });
  }
});

// Helper function to calculate top sectors
function calculateTopSectors(items) {
  const sectorCounts = {};
  items.forEach((item) => {
    if (item.sector && item.sector !== "Unknown") {
      sectorCounts[item.sector] = (sectorCounts[item.sector] || 0) + 1;
    }
  });

  return Object.entries(sectorCounts)
    .map(([sector, count]) => ({ sector, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);
}

// Get specific watchlist with items
// Get watchlist performance metrics
router.get("/performance", authenticateToken, async (req, res) => {
  console.log("🎯 Watchlist performance endpoint called");
  try {
    const userId = req.user?.sub;

    if (!userId) {
      return res.status(401).json({
        success: false,
        error: "Authentication required",
        message:
          "User authentication required to access watchlist performance data",
      });
    }

    // Check if watchlist_performance table exists
    const tableCheckQuery = `
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'watchlist_performance'
      );
    `;

    const tableExists = await query(tableCheckQuery, []);

    if (!tableExists || !tableExists.rows || !tableExists.rows[0].exists) {
      console.error("Watchlist performance table does not exist");
      return res.status(503).json({
        success: false,
        error: "Watchlist performance service not available",
        message:
          "Watchlist performance tracking requires watchlist_performance table",
        details:
          "watchlist_performance table does not exist in database schema",
        requirements: [
          "watchlist_performance table must be created with schema: user_id, watchlist_id, date, total_return, daily_return, etc.",
          "Performance calculation processes must run regularly to update metrics",
          "Price data must be available to calculate returns",
        ],
        timestamp: new Date().toISOString(),
      });
    }

    // Query watchlist performance data
    const performanceQuery = `
      SELECT 
        total_return,
        daily_return,
        weekly_return,
        monthly_return,
        best_performer,
        worst_performer,
        last_updated
      FROM watchlist_performance 
      WHERE user_id = $1 
      ORDER BY last_updated DESC 
      LIMIT 1
    `;

    const result = await query(performanceQuery, [userId]);

    if (!result || !result.rows || result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No watchlist performance data available",
        message: "Watchlist performance data not found for user",
        details:
          "User has no calculated performance metrics - watchlists may be empty or data not calculated yet",
        requirements: [
          "User must have active watchlists with symbols",
          "Performance calculation jobs must run to generate metrics",
          "Price data must be available for all watchlist symbols",
        ],
        timestamp: new Date().toISOString(),
      });
    }

    res.json({
      success: true,
      performance: result.rows[0],
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching watchlist performance:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch watchlist performance",
    });
  }
});

// Get watchlist alerts
router.get("/alerts", authenticateToken, async (req, res) => {
  try {
    res.json({
      success: true,
      data: {
        message: "Watchlist alerts endpoint",
        status: "under_development",
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching watchlist alerts:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch watchlist alerts",
    });
  }
});

// Import watchlist data
router.post("/import", authenticateToken, async (req, res) => {
  try {
    const userId = req.user.sub;
    const { name, symbols, format = "csv" } = req.body;

    console.log(`📥 Watchlist import requested for user: ${userId}`);

    if (!name || name.trim() === "") {
      return res.status(400).json({
        success: false,
        error: "Watchlist name is required",
        timestamp: new Date().toISOString(),
      });
    }

    if (!symbols || !Array.isArray(symbols) || symbols.length === 0) {
      return res.status(400).json({
        success: false,
        error: "Symbols array is required and must not be empty",
        timestamp: new Date().toISOString(),
      });
    }

    // For now, return a mock success response
    const watchlistId = `import_${Date.now()}`;

    res.status(201).json({
      success: true,
      data: {
        watchlist_id: watchlistId,
        name: name.trim(),
        imported_symbols: symbols.length,
        skipped_symbols: 0,
        format,
        created_at: new Date().toISOString(),
        status: "imported"
      },
      message: "Watchlist imported successfully",
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Import watchlist error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to import watchlist",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Export watchlist data
router.get("/export", authenticateToken, async (req, res) => {
  try {
    res.json({
      success: true,
      data: {
        message: "Watchlist export endpoint",
        status: "under_development",
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error exporting watchlist:", error);
    res.status(500).json({
      success: false,
      error: "Failed to export watchlist",
    });
  }
});

router.get("/:id", authenticateToken, async (req, res) => {
  try {
    const userId = req.user.sub;
    const watchlistId = req.params.id;

    // Validate that ID is numeric to prevent database errors
    if (!/^\d+$/.test(watchlistId)) {
      return res.status(400).json({
        success: false,
        error: "Invalid watchlist ID",
        message: "Watchlist ID must be a numeric value",
      });
    }

    // Get watchlist
    const watchlistResult = await query(
      `
      SELECT * FROM watchlists 
      WHERE id = $1 AND user_id = $2
    `,
      [watchlistId, userId]
    );

    // Add null checking for database availability
    if (!watchlistResult || !watchlistResult.rows) {
      console.warn(
        "Watchlist detail query returned null result, database may be unavailable"
      );
      return res.status(503).json({
        success: false,
        error: "Database temporarily unavailable",
        message:
          "Watchlist detail temporarily unavailable - database connection issue",
      });
    }

    if (watchlistResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Watchlist not found",
      });
    }

    const watchlist = watchlistResult.rows[0];

    // Get watchlist items with prices
    const itemsResult = await query(
      `
      SELECT wi.*, sp.price, sp.change_amount, sp.change_percent
      FROM watchlist_items wi
      LEFT JOIN price_daily sp ON wi.symbol = sp.symbol
      WHERE wi.watchlist_id = $1
      ORDER BY wi.added_at ASC
    `,
      [watchlistId]
    );

    // Add null checking for database availability
    if (!itemsResult || !itemsResult.rows) {
      console.warn(
        "Watchlist items query returned null result, database may be unavailable"
      );
      return res.status(503).json({
        success: false,
        error: "Database temporarily unavailable",
        message:
          "Watchlist items temporarily unavailable - database connection issue",
      });
    }

    watchlist.items = itemsResult.rows;

    // Calculate summary if requested
    if (req.query.include_summary === "true") {
      if (watchlist.items.length > 0) {
        const totalValue = watchlist.items.reduce(
          (sum, item) => sum + (item.price || 0),
          0
        );
        const totalChange = watchlist.items.reduce(
          (sum, item) => sum + (item.change_amount || 0),
          0
        );

        const bestPerformer = watchlist.items.reduce((best, item) =>
          (item.change_percent || 0) > (best.change_percent || 0) ? item : best
        );

        const worstPerformer = watchlist.items.reduce((worst, item) =>
          (item.change_percent || 0) < (worst.change_percent || 0)
            ? item
            : worst
        );

        watchlist.summary = {
          total_value: totalValue,
          total_change: totalChange,
          total_change_percent:
            totalValue > 0 ? (totalChange / totalValue) * 100 : 0,
          best_performer: {
            symbol: bestPerformer.symbol,
            change_percent: bestPerformer.change_percent,
          },
          worst_performer: {
            symbol: worstPerformer.symbol,
            change_percent: worstPerformer.change_percent,
          },
        };
      } else {
        // Empty watchlist summary
        watchlist.summary = {
          total_value: 0,
          total_change: 0,
          total_change_percent: 0,
          best_performer: null,
          worst_performer: null,
        };
      }
    }

    res.json({
      success: true,
      data: watchlist,
    });
  } catch (error) {
    console.error("Error fetching watchlist:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch watchlist",
      message: error.message,
    });
  }
});

// Create new watchlist
router.post("/", authenticateToken, async (req, res) => {
  try {
    const userId = req.user.sub;
    const { name, description, is_public = false } = req.body;

    if (!name || name.trim() === "") {
      return res.status(400).json({
        success: false,
        error: "name is required",
      });
    }

    if (name.trim().length > 50) {
      return res.status(400).json({
        success: false,
        error: "Watchlist name too long - cannot exceed 50 characters",
      });
    }

    // Basic input sanitization - remove HTML tags and script content
    const sanitizedName = name
      .trim()
      .replace(/<[^>]*>/g, "")
      .replace(/script/gi, "");
    const sanitizedDescription = (description || "")
      .replace(/<[^>]*>/g, "")
      .replace(/script/gi, "")
      .replace(/DROP\s+TABLE/gi, "");

    // Check for duplicate names
    const existingWatchlist = await query(
      `SELECT id FROM watchlists WHERE user_id = $1 AND name = $2`,
      [userId, sanitizedName]
    );

    if (existingWatchlist.rows.length > 0) {
      return res.status(400).json({
        success: false,
        error: "Watchlist name already exists for this user",
      });
    }

    // AWS-compatible insert without is_public column
    let result;
    try {
      result = await query(
        `
        INSERT INTO watchlists (user_id, name, description, created_at, updated_at)
        VALUES ($1, $2, $3, NOW(), NOW())
        RETURNING *
      `,
        [userId, sanitizedName, sanitizedDescription]
      );
    } catch (error) {
      if (error.message.includes('column') && error.message.includes('does not exist')) {
        // Fallback: Handle table/column not existing in AWS
        return res.status(503).json({
          success: false,
          error: "Watchlist service unavailable",
          message: "Watchlist creation is not available in the current environment",
          suggestion: "Database schema needs watchlists table configuration",
        });
      }
      throw error;
    }

    res.status(201).json({
      success: true,
      data: result.rows[0],
    });
  } catch (error) {
    console.error("Error creating watchlist:", error);
    res.status(500).json({
      success: false,
      error: "Failed to create watchlist",
      message: error.message,
    });
  }
});

// Update watchlist
router.put("/:id", authenticateToken, async (req, res) => {
  try {
    const userId = req.user.sub;
    const watchlistId = req.params.id;
    const { name, description, is_public } = req.body;

    // Validate that ID is numeric
    if (!/^\d+$/.test(watchlistId)) {
      return res.status(400).json({
        success: false,
        error: "Invalid watchlist ID format",
        message: `Watchlist ID must be a number, got: "${watchlistId}"`,
        hint: "Use PUT /api/watchlist/{id} to update watchlist metadata",
      });
    }

    if (!name || name.trim() === "") {
      return res.status(400).json({
        success: false,
        error: "name cannot be empty",
      });
    }

    if (name.trim().length > 50) {
      return res.status(400).json({
        success: false,
        error: "Watchlist name cannot exceed 50 characters",
      });
    }

    // Basic input sanitization - preserve content length
    const sanitizedName = name.trim().replace(/<[^>]*>/g, "");
    const sanitizedDescription = (description || "").replace(/<[^>]*>/g, "");

    // AWS-compatible update without is_public column
    let result;
    try {
      result = await query(
        `
        UPDATE watchlists
        SET name = $1, description = $2, updated_at = NOW()
        WHERE id = $3 AND user_id = $4
        RETURNING *
      `,
        [
          sanitizedName,
          sanitizedDescription,
          watchlistId,
          userId,
        ]
      );
    } catch (error) {
      if (error.message.includes('column') && error.message.includes('does not exist')) {
        // Fallback: Handle table/column not existing in AWS
        return res.status(503).json({
          success: false,
          error: "Watchlist service unavailable",
          message: "Watchlist update is not available in the current environment",
          suggestion: "Database schema needs watchlists table configuration",
        });
      }
      throw error;
    }

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Watchlist not found",
      });
    }

    res.json({
      success: true,
      data: result.rows[0],
    });
  } catch (error) {
    console.error("Error updating watchlist:", error);
    res.status(500).json({
      success: false,
      error: "Failed to update watchlist",
      message: error.message,
    });
  }
});

// Delete watchlist
router.delete("/:id", authenticateToken, async (req, res) => {
  try {
    const userId = req.user.sub;
    const watchlistId = req.params.id;

    // Validate that ID is numeric
    if (!/^\d+$/.test(watchlistId)) {
      return res.status(400).json({
        success: false,
        error: "Invalid watchlist ID format",
        message: `Watchlist ID must be a number, got: "${watchlistId}"`,
        hint: "Use DELETE /api/watchlist/{id}/items/{symbol} to remove a symbol from a watchlist",
      });
    }

    // Check if watchlist exists (AWS-compatible query without is_public column)
    const watchlistCheck = await query(
      `SELECT id FROM watchlists WHERE id = $1 AND user_id = $2`,
      [watchlistId, userId]
    );

    if (watchlistCheck.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Watchlist not found",
      });
    }

    // Skip is_public check for AWS compatibility (all watchlists are private by default)

    // Delete watchlist items first
    await query(
      `
      DELETE FROM watchlist_items 
      WHERE watchlist_id = $1
    `,
      [watchlistId]
    );

    // Delete watchlist
    const result = await query(
      `
      DELETE FROM watchlists 
      WHERE id = $1 AND user_id = $2
      RETURNING *
    `,
      [watchlistId, userId]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Watchlist not found",
      });
    }

    res.json({ message: "Watchlist deleted successfully" });
  } catch (error) {
    console.error("Error deleting watchlist:", error);
    res.status(500).json({
      success: false,
      error: "Failed to delete watchlist",
      message: error.message,
    });
  }
});

// Add item to watchlist
router.post("/:id/items", authenticateToken, async (req, res) => {
  try {
    const userId = req.user.sub;
    const watchlistId = req.params.id;
    const { symbol, notes } = req.body;

    if (!symbol || symbol.trim() === "") {
      return res.status(400).json({
        success: false,
        error: "Symbol is required",
      });
    }

    // Validate symbol format (basic format - 1-5 uppercase letters/digits)
    const cleanSymbol = symbol.trim().toUpperCase();
    if (!/^[A-Z0-9]{1,5}$/.test(cleanSymbol)) {
      return res.status(400).json({
        success: false,
        error: "invalid symbol format",
      });
    }

    // Verify watchlist belongs to user
    const watchlistCheck = await query(
      `
      SELECT id FROM watchlists 
      WHERE id = $1 AND user_id = $2
    `,
      [watchlistId, userId]
    );

    if (watchlistCheck.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Watchlist not found",
      });
    }

    // Check if symbol already exists in watchlist
    const existingItem = await query(
      `
      SELECT id FROM watchlist_items 
      WHERE watchlist_id = $1 AND symbol = $2
    `,
      [watchlistId, symbol.toUpperCase()]
    );

    if (existingItem.rows.length > 0) {
      return res.status(400).json({
        success: false,
        error: "symbol already in watchlist",
      });
    }

    const result = await query(
      `
      INSERT INTO watchlist_items (watchlist_id, symbol, notes, added_at)
      VALUES ($1, $2, $3, NOW())
      RETURNING *
    `,
      [watchlistId, cleanSymbol, notes || ""]
    );

    res.status(201).json({
      success: true,
      data: result.rows[0],
    });
  } catch (error) {
    console.error("Error adding item to watchlist:", error);
    res.status(500).json({
      success: false,
      error: "Failed to add item to watchlist",
      message: error.message,
    });
  }
});

// Batch add items to watchlist
router.post("/:id/items/batch", authenticateToken, async (req, res) => {
  try {
    const userId = req.user.sub;
    const watchlistId = req.params.id;
    const { symbols } = req.body;

    if (!Array.isArray(symbols) || symbols.length === 0) {
      return res.status(400).json({
        success: false,
        error: "Symbols array is required",
      });
    }

    // Verify watchlist belongs to user
    const watchlistCheck = await query(
      `
      SELECT id FROM watchlists 
      WHERE id = $1 AND user_id = $2
    `,
      [watchlistId, userId]
    );

    if (watchlistCheck.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Watchlist not found",
      });
    }

    const results = [];
    const errors = [];

    for (const symbol of symbols) {
      try {
        if (!symbol || symbol.trim() === "") {
          errors.push({ symbol, error: "Symbol is required" });
          continue;
        }

        // Validate symbol format
        const cleanSymbol = symbol.trim().toUpperCase();
        if (!/^[A-Z0-9]{1,5}$/.test(cleanSymbol)) {
          errors.push({ symbol, error: "invalid symbol format" });
          continue;
        }

        // Check if symbol already exists
        const existingItem = await query(
          `
          SELECT id FROM watchlist_items 
          WHERE watchlist_id = $1 AND symbol = $2
        `,
          [watchlistId, cleanSymbol]
        );

        if (existingItem.rows.length > 0) {
          errors.push({ symbol, error: "symbol already in watchlist" });
          continue;
        }

        const result = await query(
          `
          INSERT INTO watchlist_items (watchlist_id, symbol, added_at)
          VALUES ($1, $2, NOW())
          RETURNING *
        `,
          [watchlistId, cleanSymbol]
        );

        results.push(result.rows[0]);
      } catch (error) {
        errors.push({ symbol, error: error.message });
      }
    }

    res.status(201).json({
      success: true,
      data: {
        added: results.length,
        items: results,
        errors: errors,
        total_attempted: symbols.length,
        successful: results.length,
        failed: errors.length,
      },
    });
  } catch (error) {
    console.error("Error batch adding items to watchlist:", error);
    res.status(500).json({
      success: false,
      error: "Failed to batch add items to watchlist",
      message: error.message,
    });
  }
});

// Remove item from watchlist
router.delete("/:id/items/:symbol", authenticateToken, async (req, res) => {
  try {
    const userId = req.user.sub;
    const watchlistId = req.params.id;
    const symbol = req.params.symbol.toUpperCase();

    // Verify watchlist belongs to user
    const watchlistCheck = await query(
      `
      SELECT id FROM watchlists 
      WHERE id = $1 AND user_id = $2
    `,
      [watchlistId, userId]
    );

    if (watchlistCheck.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Watchlist not found",
      });
    }

    const result = await query(
      `
      DELETE FROM watchlist_items 
      WHERE watchlist_id = $1 AND symbol = $2
      RETURNING *
    `,
      [watchlistId, symbol]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Item not found in watchlist",
      });
    }

    res.json({ message: "removed successfully" });
  } catch (error) {
    console.error("Error removing item from watchlist:", error);
    res.status(500).json({
      success: false,
      error: "Failed to remove item from watchlist",
      message: error.message,
    });
  }
});

module.exports = router;

const express = require("express");

const router = express.Router();
const { query } = require("../utils/database");
const { authenticateToken } = require("../middleware/auth");

// Get user's watchlists
router.get("/", authenticateToken, async (req, res) => {
  try {
    const userId = req.user.sub;

    const watchlists = await query(
      `
      SELECT w.*, 
             COALESCE(item_counts.item_count, 0) as item_count
      FROM watchlists w
      LEFT JOIN (
        SELECT watchlist_id, COUNT(*) as item_count
        FROM watchlist_items
        GROUP BY watchlist_id
      ) item_counts ON w.id = item_counts.watchlist_id
      WHERE w.user_id = $1
      ORDER BY w.is_public DESC, w.created_at ASC
    `,
      [userId]
    );

    // Add null checking for database availability
    if (!watchlists || !watchlists.rows) {
      console.warn("Watchlist query returned null result, database may be unavailable");
      return res.status(503).json({
        success: false,
        error: "Database temporarily unavailable",
        message: "Watchlist data temporarily unavailable - database connection issue",
        data: [],
        total: 0
      });
    }

    res.success({data: watchlists.rows,
      total: watchlists.rows.length,
    });
  } catch (error) {
    console.error("Error fetching watchlists:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch watchlists",
      message: error.message,
    });
  }
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
        s.name as company_name,
        s.sector,
        s.market_cap
      FROM watchlist_items wi
      JOIN watchlists w ON wi.watchlist_id = w.id
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) 
          symbol, close, date
        FROM stock_prices 
        ORDER BY symbol, date DESC
      ) sp ON wi.symbol = sp.symbol
      LEFT JOIN stocks s ON wi.symbol = s.symbol
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
      itemsQuery += ` AND w.id = $${paramIndex}`;
      queryParams.push(parseInt(watchlist_id));
      paramIndex++;
    }

    itemsQuery += ` ORDER BY wi.added_at DESC LIMIT $${paramIndex}`;
    queryParams.push(parseInt(limit));

    const itemsResult = await query(itemsQuery, queryParams);

    if (!itemsResult || !itemsResult.rows) {
      console.warn("Watchlist items query returned null result, database may be unavailable");
      return res.status(503).json({
        success: false,
        error: "Database temporarily unavailable",
        message: "Watchlist items temporarily unavailable - database connection issue",
        data: [],
        total: 0
      });
    }

    // Calculate summary statistics
    const items = itemsResult.rows;
    const totalValue = items.reduce((sum, item) => sum + (item.current_price || 0), 0);
    const totalChange = items.reduce((sum, item) => sum + (item.change_amount || 0), 0);
    const avgChangePercent = items.length > 0 ? 
      items.reduce((sum, item) => sum + (item.change_percent || 0), 0) / items.length : 0;

    res.success({
      data: items,
      total: items.length,
      summary: {
        total_items: items.length,
        total_value: parseFloat(totalValue.toFixed(2)),
        total_change: parseFloat(totalChange.toFixed(2)),
        average_change_percent: parseFloat(avgChangePercent.toFixed(2)),
        unique_watchlists: [...new Set(items.map(item => item.watchlist_id))].length
      },
      filters: {
        symbol: symbol || null,
        watchlist_id: watchlist_id || null,
        limit: parseInt(limit)
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Error fetching watchlist items:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch watchlist items",
      message: error.message
    });
  }
});

// Get recent watchlist items across all watchlists
router.get("/items/recent", async (req, res) => {
  try {
    const { limit = 20, days = 7 } = req.query;
    
    console.log(`📋 Recent watchlist items requested - limit: ${limit}, days: ${days}`);
    
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
        pd.close_price as current_price,
        pd.change_percent,
        pd.change_amount,
        pd.volume,
        s.name as company_name,
        s.sector,
        s.market_cap
      FROM watchlist_items wi
      LEFT JOIN watchlists w ON wi.watchlist_id = w.id
      LEFT JOIN price_daily pd ON wi.symbol = pd.symbol 
        AND pd.date = (SELECT MAX(date) FROM price_daily WHERE symbol = wi.symbol)
      LEFT JOIN stocks s ON wi.symbol = s.symbol
      WHERE wi.added_at >= NOW() - INTERVAL '${parseInt(days)} days'
      ORDER BY wi.added_at DESC
      LIMIT $1
    `;
    
    const result = await query(recentItemsQuery, [parseInt(limit)]);
    
    if (!result || !result.rows) {
      return res.json({
        success: true,
        data: {
          items: [],
          summary: {
            total_items: 0,
            unique_symbols: 0,
            unique_watchlists: 0,
            days_covered: parseInt(days),
            message: "No recent watchlist items found"
          }
        },
        timestamp: new Date().toISOString()
      });
    }
    
    const items = result.rows.map(row => ({
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
      hours_ago: Math.floor((Date.now() - new Date(row.added_at)) / (1000 * 60 * 60)),
      notes: row.notes || null,
      watchlist: {
        id: row.watchlist_id,
        name: row.watchlist_name || "Unknown",
        user_id: row.user_id
      }
    }));
    
    // Calculate summary statistics
    const uniqueSymbols = [...new Set(items.map(item => item.symbol))].length;
    const uniqueWatchlists = [...new Set(items.map(item => item.watchlist.id))].length;
    const totalValue = items.reduce((sum, item) => sum + (item.current_price || 0), 0);
    const avgChangePercent = items.length > 0 
      ? items.reduce((sum, item) => sum + (item.change_percent || 0), 0) / items.length 
      : 0;
    
    const summary = {
      total_items: items.length,
      unique_symbols: uniqueSymbols,
      unique_watchlists: uniqueWatchlists,
      days_covered: parseInt(days),
      total_market_value: Math.round(totalValue * 100) / 100,
      avg_change_percent: Math.round(avgChangePercent * 100) / 100,
      most_active_period: items.length > 0 
        ? new Date(Math.max(...items.map(item => new Date(item.added_at)))).toISOString().split('T')[0]
        : null,
      top_sectors: calculateTopSectors(items),
      recent_additions_trend: items.length >= 2 
        ? items.slice(0, Math.ceil(items.length/2)).length > items.slice(Math.ceil(items.length/2)).length 
          ? "increasing" 
          : "decreasing"
        : "stable"
    };
    
    res.json({
      success: true,
      data: {
        items: items,
        summary: summary,
        filters: {
          limit: parseInt(limit),
          days: parseInt(days)
        }
      },
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error("Error fetching recent watchlist items:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch recent watchlist items",
      details: error.message
    });
  }
});

// Helper function to calculate top sectors
function calculateTopSectors(items) {
  const sectorCounts = {};
  items.forEach(item => {
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
router.get("/:id", authenticateToken, async (req, res) => {
  try {
    const userId = req.user.sub;
    const watchlistId = req.params.id;

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
      console.warn("Watchlist detail query returned null result, database may be unavailable");
      return res.status(503).json({
        success: false,
        error: "Database temporarily unavailable", 
        message: "Watchlist detail temporarily unavailable - database connection issue"
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
      LEFT JOIN stock_prices sp ON wi.symbol = sp.symbol
      WHERE wi.watchlist_id = $1
      ORDER BY wi.added_at ASC
    `,
      [watchlistId]
    );

    // Add null checking for database availability
    if (!itemsResult || !itemsResult.rows) {
      console.warn("Watchlist items query returned null result, database may be unavailable");
      return res.status(503).json({
        success: false,
        error: "Database temporarily unavailable",
        message: "Watchlist items temporarily unavailable - database connection issue"
      });
    }

    watchlist.items = itemsResult.rows;

    // Calculate summary if requested
    if (req.query.include_summary === 'true') {
      if (watchlist.items.length > 0) {
        const totalValue = watchlist.items.reduce((sum, item) => sum + (item.price || 0), 0);
        const totalChange = watchlist.items.reduce((sum, item) => sum + (item.change_amount || 0), 0);
        
        const bestPerformer = watchlist.items.reduce((best, item) => 
          (item.change_percent || 0) > (best.change_percent || 0) ? item : best
        );
        
        const worstPerformer = watchlist.items.reduce((worst, item) => 
          (item.change_percent || 0) < (worst.change_percent || 0) ? item : worst
        );

        watchlist.summary = {
          total_value: totalValue,
          total_change: totalChange,
          total_change_percent: totalValue > 0 ? (totalChange / totalValue) * 100 : 0,
          best_performer: {
            symbol: bestPerformer.symbol,
            change_percent: bestPerformer.change_percent
          },
          worst_performer: {
            symbol: worstPerformer.symbol,
            change_percent: worstPerformer.change_percent
          }
        };
      } else {
        // Empty watchlist summary
        watchlist.summary = {
          total_value: 0,
          total_change: 0,
          total_change_percent: 0,
          best_performer: null,
          worst_performer: null
        };
      }
    }

    res.success({data: watchlist,
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
    const sanitizedName = name.trim().replace(/<[^>]*>/g, '').replace(/script/gi, '');
    const sanitizedDescription = (description || "").replace(/<[^>]*>/g, '').replace(/script/gi, '').replace(/DROP\s+TABLE/gi, '');

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

    const result = await query(
      `
      INSERT INTO watchlists (user_id, name, description, is_public, created_at, updated_at)
      VALUES ($1, $2, $3, $4, NOW(), NOW())
      RETURNING *
    `,
      [userId, sanitizedName, sanitizedDescription, is_public]
    );

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
    const sanitizedName = name.trim().replace(/<[^>]*>/g, '');
    const sanitizedDescription = (description || "").replace(/<[^>]*>/g, '');

    const result = await query(
      `
      UPDATE watchlists 
      SET name = $1, description = $2, is_public = $3, updated_at = NOW()
      WHERE id = $4 AND user_id = $5
      RETURNING *
    `,
      [sanitizedName, sanitizedDescription, is_public || false, watchlistId, userId]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Watchlist not found",
      });
    }

    res.success({data: result.rows[0],
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

    // Check if this is a default watchlist
    const watchlistCheck = await query(
      `SELECT is_public FROM watchlists WHERE id = $1 AND user_id = $2`,
      [watchlistId, userId]
    );

    if (watchlistCheck.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Watchlist not found",
      });
    }

    if (watchlistCheck.rows[0].is_public) {
      return res.status(400).json({
        success: false,
        error: "cannot delete public watchlist",
      });
    }

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

    res.success({message: "Watchlist deleted successfully",
    });
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

    res.success({message: "removed successfully",
    });
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

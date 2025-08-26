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
      ORDER BY w.is_default DESC, w.created_at ASC
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
    const { name, description, is_default = false } = req.body;

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
      INSERT INTO watchlists (user_id, name, description, is_default, created_at, updated_at)
      VALUES ($1, $2, $3, $4, NOW(), NOW())
      RETURNING *
    `,
      [userId, sanitizedName, sanitizedDescription, is_default]
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
    const { name, description, is_default } = req.body;

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
      SET name = $1, description = $2, is_default = $3, updated_at = NOW()
      WHERE id = $4 AND user_id = $5
      RETURNING *
    `,
      [sanitizedName, sanitizedDescription, is_default || false, watchlistId, userId]
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
      `SELECT is_default FROM watchlists WHERE id = $1 AND user_id = $2`,
      [watchlistId, userId]
    );

    if (watchlistCheck.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Watchlist not found",
      });
    }

    if (watchlistCheck.rows[0].is_default) {
      return res.status(400).json({
        success: false,
        error: "cannot delete default watchlist",
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

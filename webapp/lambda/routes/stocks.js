const express = require("express");
const { query } = require("../utils/database");

const router = express.Router();

// GET /api/stocks - List all stocks
router.get("/", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 100, 1000);
    const offset = parseInt(req.query.offset) || 0;

    const result = await query(
      "SELECT id, symbol, name, sector, industry FROM stocks ORDER BY symbol LIMIT $1 OFFSET $2",
      [limit, offset]
    );

    const countResult = await query("SELECT COUNT(*) as total FROM stocks");
    const total = parseInt(countResult.rows[0].total);

    res.json({
      success: true,
      data: result.rows,
      pagination: {
        limit,
        offset,
        total
      }
    });
  } catch (error) {
    console.error("Error fetching stocks:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch stocks",
      message: error.message
    });
  }
});

// GET /api/stocks/:symbol - Get specific stock
router.get("/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;

    const result = await query(
      "SELECT id, symbol, name, sector, industry FROM stocks WHERE symbol = $1",
      [symbol.toUpperCase()]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Stock not found"
      });
    }

    res.json({
      success: true,
      data: result.rows[0]
    });
  } catch (error) {
    console.error("Error fetching stock:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch stock",
      message: error.message
    });
  }
});

module.exports = router;

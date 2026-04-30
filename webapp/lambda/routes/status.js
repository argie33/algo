const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError } = require("../utils/apiResponse");
const router = express.Router();

// GET /api/status - Quick API status check
router.get("/", async (req, res) => {
  try {
    // Quick health check
    const result = await query("SELECT COUNT(*) as count FROM stock_symbols");
    const symbolCount = parseInt(result.rows[0].count);

    return sendSuccess(res, {
      status: "ok",
      timestamp: new Date().toISOString(),
      uptime: process.uptime(),
      database: {
        connected: true,
        stocks: symbolCount
      }
    });
  } catch (error) {
    const errorMsg = error && typeof error === 'object' ? (error.message || String(error)) : String(error);
    return sendSuccess(res, {
      status: "error",
      timestamp: new Date().toISOString(),
      error: errorMsg
    }, 503);
  }
});

module.exports = router;

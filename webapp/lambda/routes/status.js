const express = require("express");

const { query } = require("../utils/database");
const { sendSuccess } = require("../utils/apiResponse");
const { validateQueryResult } = require("../utils/responseValidation");
const logger = require("../utils/logger");
const router = express.Router();

// GET /api/status - Quick API status check
router.get("/", async (req, res) => {
  try {
    // Quick health check
    const result = await query("SELECT COUNT(*) as count FROM stock_symbols");
    validateQueryResult(result, { requireRows: false });
    const symbolCount = parseInt(result.rows[0].count);

    return sendSuccess(res, {
      status: "ok",
      timestamp: new Date().toISOString(),
      uptime: process.uptime(),
      database: {
        connected: true,
        stocks: symbolCount,
      },
    });
  } catch (error) {
    const errorMsg =
      error && typeof error === "object"
        ? error.message || String(error)
        : String(error);
    logger.error("Error in /status:", { error: errorMsg, stack: error?.stack });
    return sendSuccess(
      res,
      {
        status: "error",
        timestamp: new Date().toISOString(),
        error: errorMsg,
      },
      503
    );
  }
});

module.exports = router;

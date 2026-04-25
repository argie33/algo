/**
 * Trading Routes
 * Alias for trades endpoints
 * Frontend expects /api/trading/* but backend calls it /api/trades
 */

const express = require("express");
const tradesRoutes = require("./trades");
const router = express.Router();

// Re-export all trades routes under trading path
router.use("/", tradesRoutes);

module.exports = router;

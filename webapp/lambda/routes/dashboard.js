/**
 * Dashboard Routes
 * Alias for diagnostics endpoints
 * Frontend expects /api/dashboard/* but backend calls it /api/diagnostics
 */

const express = require("express");
const diagnosticsRoutes = require("./diagnostics");
const router = express.Router();

// Re-export all diagnostics routes under dashboard path
// This allows frontend to call /api/dashboard/* which maps to diagnostics logic
router.use("/", diagnosticsRoutes);

module.exports = router;

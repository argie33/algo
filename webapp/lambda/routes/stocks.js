const express = require("express");

const router = express.Router();

// Root endpoint - redirect to scores endpoint
router.get("/", (req, res) => {
  return res.json({
    data: {
      message: "Stock data endpoints have been consolidated",
      status: "consolidated",
      note: "Use /api/scores/stockscores for stock screening with comprehensive metrics",
      available_routes: [
        "/api/scores/stockscores - Stock screening with financial filters (paginated)"
      ]
    },
    success: true
  });
});

module.exports = router;

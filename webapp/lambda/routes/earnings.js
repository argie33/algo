const express = require("express");

const calendarRouter = require("./calendar");

const router = express.Router();

// Earnings data - delegate to calendar earnings endpoints
router.get("/", async (req, res) => {
  try {
    console.log(`📈 Earnings data requested - delegating to calendar/earnings`);
    
    // Create a mock request/response to call calendar earnings internally
    const mockReq = {
      ...req,
      url: '/earnings',
      path: '/earnings',
      route: { path: '/earnings' }
    };
    
    // Call calendar earnings handler
    return calendarRouter.handle(mockReq, res, (err) => {
      if (err) {
        console.error("Calendar earnings delegation error:", err);
        return res.status(500).json({
          success: false,
          error: "Failed to fetch earnings data",
          details: err.message,
          timestamp: new Date().toISOString()
        });
      }
    });

  } catch (error) {
    console.error("Earnings delegation error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch earnings data",
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get earnings details for specific symbol - delegate to calendar
router.get("/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    console.log(`📊 Earnings details for ${symbol} - delegating to calendar/earnings`);
    
    // Modify query to include symbol filter and delegate to calendar
    const mockReq = {
      ...req,
      url: '/earnings',
      path: '/earnings',
      route: { path: '/earnings' },
      query: {
        ...req.query,
        symbol: symbol.toUpperCase()
      }
    };
    
    return calendarRouter.handle(mockReq, res, (err) => {
      if (err) {
        console.error("Calendar earnings delegation error:", err);
        return res.status(500).json({
          success: false,
          error: "Failed to fetch earnings details",
          details: err.message,
          symbol: symbol.toUpperCase(),
          timestamp: new Date().toISOString()
        });
      }
    });

  } catch (error) {
    console.error(`Earnings delegation error for ${req.params.symbol}:`, error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch earnings details",
      details: error.message,
      symbol: req.params.symbol?.toUpperCase() || null,
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;
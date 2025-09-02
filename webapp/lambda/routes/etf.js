const express = require("express");

const { query } = require("../utils/database");

const router = express.Router();

// ETF holdings endpoint
router.get("/:symbol/holdings", async (req, res) => {
  try {
    const { symbol } = req.params;
    const { limit = 25 } = req.query;
    console.log(`📈 ETF holdings requested for ${symbol}`);

    if (!symbol) {
      return res.status(400).json({
        success: false,
        error: "ETF symbol is required",
        message: "Please provide a valid ETF symbol"
      });
    }

    // Get ETF holdings from database
    const holdingsResult = await query(`
      SELECT 
        h.holding_symbol, h.company_name, h.weight_percent, 
        h.shares_held, h.market_value, h.sector,
        e.fund_name, e.total_assets, e.expense_ratio, e.dividend_yield
      FROM etf_holdings h
      JOIN etfs e ON h.etf_symbol = e.symbol
      WHERE h.etf_symbol = $1 
      ORDER BY h.weight_percent DESC
      LIMIT $2
    `, [symbol.toUpperCase(), parseInt(limit)]);

    if (!holdingsResult.rows || holdingsResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "ETF not found",
        message: `No holdings data found for ETF symbol: ${symbol.toUpperCase()}. Please verify the symbol is correct.`
      });
    }

    // Get sector allocation
    const sectorResult = await query(`
      SELECT sector, SUM(weight_percent) as total_weight
      FROM etf_holdings 
      WHERE etf_symbol = $1 
      GROUP BY sector
      ORDER BY total_weight DESC
    `, [symbol.toUpperCase()]);

    const holdings = holdingsResult.rows.map(row => ({
      symbol: row.holding_symbol,
      company_name: row.company_name,
      weight_percent: parseFloat(row.weight_percent),
      shares_held: parseInt(row.shares_held),
      market_value: parseFloat(row.market_value),
      sector: row.sector
    }));

    const sectorAllocation = {};
    sectorResult.rows.forEach(row => {
      sectorAllocation[row.sector.toLowerCase().replace(/\s+/g, '_')] = parseFloat(row.total_weight);
    });

    const holdingsData = {
      etf_symbol: symbol.toUpperCase(),
      fund_name: holdingsResult.rows[0].fund_name,
      total_assets: holdingsResult.rows[0].total_assets,
      
      top_holdings: holdings,
      sector_allocation: sectorAllocation,
      
      fund_metrics: {
        expense_ratio: parseFloat(holdingsResult.rows[0].expense_ratio || 0),
        total_holdings: holdings.length,
        aum: parseFloat(holdingsResult.rows[0].total_assets || 0),
        dividend_yield: parseFloat(holdingsResult.rows[0].dividend_yield || 0)
      },
      
      last_updated: new Date().toISOString()
    };

    res.json({
      success: true,
      data: holdingsData,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("ETF holdings database error:", error);
    
    if (error.code === '42P01') {
      return res.status(500).json({
        success: false,
        error: "Database table not found",
        message: "ETF holdings table does not exist. Please contact support."
      });
    }

    res.status(500).json({
      success: false,
      error: "Failed to fetch ETF holdings",
      message: "Database query failed. Please try again later."
    });
  }
});

module.exports = router;
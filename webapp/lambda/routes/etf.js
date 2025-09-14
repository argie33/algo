const express = require("express");

const { query } = require("../utils/database");

const router = express.Router();

// Root endpoint - API info
router.get("/", async (req, res) => {
  res.json({
    success: true,
    data: []
  });
});

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

// ETF analytics endpoint
router.get("/:symbol/analytics", async (req, res) => {
  try {
    const { symbol } = req.params;
    const { period = "1y" } = req.query;
    console.log(`📊 ETF analytics requested for ${symbol}, period: ${period}`);

    if (!symbol) {
      return res.status(400).json({
        success: false,
        error: "ETF symbol is required",
        message: "Please provide a valid ETF symbol"
      });
    }

    // Get ETF basic information and recent performance data
    const etfResult = await query(`
      SELECT 
        e.symbol, e.fund_name, e.total_assets, e.expense_ratio, 
        e.dividend_yield, e.inception_date, e.category, e.strategy,
        p.close as current_price, p.change_percent as daily_change
      FROM etfs e
      LEFT JOIN price_daily p ON e.symbol = p.symbol 
        AND p.date = (SELECT MAX(date) FROM price_daily WHERE symbol = e.symbol)
      WHERE e.symbol = $1
    `, [symbol.toUpperCase()]);

    if (!etfResult.rows || etfResult.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "ETF not found",
        message: `ETF symbol ${symbol.toUpperCase()} not found in database. Please verify the symbol is correct.`,
        details: {
          requested_symbol: symbol.toUpperCase(),
          suggestion: "Use /api/etf to see available ETFs"
        }
      });
    }

    const etfInfo = etfResult.rows[0];

    // Get price history for performance calculations
    const periodDays = { "1m": 30, "3m": 90, "6m": 180, "1y": 365, "2y": 730 };
    const days = periodDays[period] || 365;

    const priceResult = await query(`
      SELECT date, close_price, volume
      FROM price_daily 
      WHERE symbol = $1 
        AND date >= CURRENT_DATE - INTERVAL '${days} days'
      ORDER BY date ASC
    `, [symbol.toUpperCase()]);

    // Calculate performance metrics if price data exists
    let performanceMetrics = {
      period_return: "0.00%",
      volatility: "0.00%",
      max_drawdown: "0.00%",
      sharpe_ratio: "N/A",
      avg_volume: 0
    };

    if (priceResult.rows && priceResult.rows.length > 1) {
      const prices = priceResult.rows.map(r => parseFloat(r.close_price));
      const volumes = priceResult.rows.map(r => parseInt(r.volume) || 0);
      
      // Period return
      const startPrice = prices[0];
      const endPrice = prices[prices.length - 1];
      const periodReturn = ((endPrice - startPrice) / startPrice * 100);
      
      // Calculate daily returns for volatility
      const dailyReturns = [];
      for (let i = 1; i < prices.length; i++) {
        const dailyReturn = (prices[i] - prices[i-1]) / prices[i-1];
        dailyReturns.push(dailyReturn);
      }
      
      // Volatility (annualized)
      const meanReturn = dailyReturns.reduce((a, b) => a + b, 0) / dailyReturns.length;
      const variance = dailyReturns.reduce((sum, ret) => sum + Math.pow(ret - meanReturn, 2), 0) / (dailyReturns.length - 1);
      const volatility = Math.sqrt(variance) * Math.sqrt(252) * 100; // Annualized
      
      // Max drawdown calculation
      let peak = prices[0];
      let maxDrawdown = 0;
      for (const price of prices) {
        if (price > peak) peak = price;
        const drawdown = (peak - price) / peak * 100;
        if (drawdown > maxDrawdown) maxDrawdown = drawdown;
      }
      
      // Sharpe ratio (assuming 2% risk-free rate)
      const annualizedReturn = meanReturn * 252 * 100;
      const sharpeRatio = volatility > 0 ? (annualizedReturn - 2) / volatility : 0;
      
      // Average volume
      const avgVolume = volumes.reduce((a, b) => a + b, 0) / volumes.length;
      
      performanceMetrics = {
        period_return: `${periodReturn.toFixed(2)}%`,
        volatility: `${volatility.toFixed(2)}%`,
        max_drawdown: `${maxDrawdown.toFixed(2)}%`,
        sharpe_ratio: sharpeRatio.toFixed(2),
        avg_volume: Math.round(avgVolume)
      };
    }

    // Get top holdings for additional context
    const holdingsResult = await query(`
      SELECT holding_symbol, company_name, weight_percent, sector
      FROM etf_holdings 
      WHERE etf_symbol = $1 
      ORDER BY weight_percent DESC 
      LIMIT 10
    `, [symbol.toUpperCase()]);

    const topHoldings = holdingsResult.rows || [];
    
    // Sector allocation
    const sectorResult = await query(`
      SELECT sector, SUM(weight_percent) as total_weight
      FROM etf_holdings 
      WHERE etf_symbol = $1 
      GROUP BY sector
      ORDER BY total_weight DESC
      LIMIT 5
    `, [symbol.toUpperCase()]);

    const sectorAllocation = sectorResult.rows || [];

    res.json({
      success: true,
      data: {
        etf_info: {
          symbol: etfInfo.symbol,
          name: etfInfo.fund_name,
          category: etfInfo.category || "N/A",
          strategy: etfInfo.strategy || "N/A",
          assets_under_management: etfInfo.total_assets ? `$${(etfInfo.total_assets / 1000000).toFixed(1)}M` : "N/A",
          expense_ratio: etfInfo.expense_ratio ? `${etfInfo.expense_ratio}%` : "N/A",
          dividend_yield: etfInfo.dividend_yield ? `${etfInfo.dividend_yield}%` : "N/A",
          inception_date: etfInfo.inception_date,
          current_price: etfInfo.current_price ? `$${parseFloat(etfInfo.current_price).toFixed(2)}` : "N/A",
          daily_change: etfInfo.daily_change ? `${parseFloat(etfInfo.daily_change).toFixed(2)}%` : "N/A"
        },
        performance: {
          period: period,
          ...performanceMetrics,
          price_history_points: priceResult.rows ? priceResult.rows.length : 0
        },
        holdings: {
          top_holdings: topHoldings.slice(0, 5).map(h => ({
            symbol: h.holding_symbol,
            name: h.company_name,
            weight: `${h.weight_percent}%`,
            sector: h.sector
          })),
          sector_allocation: sectorAllocation.map(s => ({
            sector: s.sector,
            weight: `${parseFloat(s.total_weight).toFixed(2)}%`
          }))
        },
        analytics_summary: {
          total_holdings: topHoldings.length,
          data_quality: priceResult.rows && priceResult.rows.length > 30 ? "Good" : "Limited",
          analysis_period: period,
          last_updated: new Date().toISOString()
        }
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error(`ETF analytics error for ${req.params.symbol}:`, error);
    
    if (error.code === '42P01') {
      return res.status(500).json({
        success: false,
        error: "Database table not found",
        message: "ETF analytics requires ETF data tables. Please contact support.",
        details: {
          required_tables: ["etfs", "etf_holdings", "price_daily"],
          error_code: error.code
        }
      });
    }

    res.status(500).json({
      success: false,
      error: "Failed to fetch ETF analytics",
      message: error.message
    });
  }
});

module.exports = router;
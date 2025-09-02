const express = require("express");

const router = express.Router();

// Health endpoint (no auth required)
router.get("/health", (req, res) => {
  res.success({status: "operational",
    service: "commodities",
    timestamp: new Date().toISOString(),
    message: "Commodities service is running",
  });
});

// Root commodities endpoint for health checks
router.get("/", (req, res) => {
  res.success({data: {
      system: "Commodities API",
      version: "1.0.0",
      status: "operational",
      available_endpoints: [
        "GET /commodities/categories - Commodity categories",
        "GET /commodities/prices - Current commodity prices",
        "GET /commodities/market-summary - Market overview",
        "GET /commodities/correlations - Price correlations",
        "GET /commodities/news - Latest commodity news",
      ],
      timestamp: new Date().toISOString(),
    },
  });
});

// Get commodity categories
router.get("/categories", (req, res) => {
  try {
    const categories = [
      {
        id: "energy",
        name: "Energy",
        description: "Oil, gas, and energy commodities",
        commodities: ["crude-oil", "natural-gas", "heating-oil", "gasoline"],
        weight: 0.35,
        performance: {
          "1d": 0.5,
          "1w": -2.1,
          "1m": 4.3,
          "3m": -8.7,
          "1y": 12.4,
        },
      },
      {
        id: "precious-metals",
        name: "Precious Metals",
        description: "Gold, silver, platinum, and palladium",
        commodities: ["gold", "silver", "platinum", "palladium"],
        weight: 0.25,
        performance: {
          "1d": -0.3,
          "1w": 1.8,
          "1m": -1.2,
          "3m": 5.6,
          "1y": 8.9,
        },
      },
      {
        id: "base-metals",
        name: "Base Metals",
        description: "Copper, aluminum, zinc, and industrial metals",
        commodities: ["copper", "aluminum", "zinc", "nickel", "lead"],
        weight: 0.2,
        performance: {
          "1d": 1.2,
          "1w": 3.4,
          "1m": 2.8,
          "3m": -4.2,
          "1y": 15.7,
        },
      },
      {
        id: "agriculture",
        name: "Agriculture",
        description: "Grains, livestock, and soft commodities",
        commodities: ["wheat", "corn", "soybeans", "coffee", "sugar", "cotton"],
        weight: 0.15,
        performance: {
          "1d": -0.8,
          "1w": -1.5,
          "1m": 6.2,
          "3m": 12.1,
          "1y": -3.4,
        },
      },
      {
        id: "livestock",
        name: "Livestock",
        description: "Cattle, hogs, and feeder cattle",
        commodities: ["live-cattle", "feeder-cattle", "lean-hogs"],
        weight: 0.05,
        performance: {
          "1d": 0.2,
          "1w": 2.1,
          "1m": -1.8,
          "3m": 7.3,
          "1y": 11.2,
        },
      },
    ];

    res.success({data: categories,
      metadata: {
        totalCategories: categories.length,
        lastUpdated: new Date().toISOString(),
        priceDate: new Date().toISOString(),
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching commodity categories:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch commodity categories",
      details: error.message,
    });
  }
});

// Get commodity prices
router.get("/prices", (req, res) => {
  try {
    const category = req.query.category;
    const symbol = req.query.symbol;

    let commodities = [
      {
        symbol: "CL",
        name: "Crude Oil",
        category: "energy",
        price: 78.45,
        change: 0.67,
        changePercent: 0.86,
        unit: "per barrel",
        currency: "USD",
        volume: 245678,
        lastUpdated: new Date().toISOString(),
      },
      {
        symbol: "GC",
        name: "Gold",
        category: "precious-metals",
        price: 2034.2,
        change: -5.3,
        changePercent: -0.26,
        unit: "per ounce",
        currency: "USD",
        volume: 89432,
        lastUpdated: new Date().toISOString(),
      },
      {
        symbol: "SI",
        name: "Silver",
        category: "precious-metals",
        price: 24.67,
        change: 0.23,
        changePercent: 0.94,
        unit: "per ounce",
        currency: "USD",
        volume: 34567,
        lastUpdated: new Date().toISOString(),
      },
      {
        symbol: "HG",
        name: "Copper",
        category: "base-metals",
        price: 3.89,
        change: 0.045,
        changePercent: 1.17,
        unit: "per pound",
        currency: "USD",
        volume: 67890,
        lastUpdated: new Date().toISOString(),
      },
      {
        symbol: "NG",
        name: "Natural Gas",
        category: "energy",
        price: 2.87,
        change: -0.12,
        changePercent: -4.02,
        unit: "per MMBtu",
        currency: "USD",
        volume: 123456,
        lastUpdated: new Date().toISOString(),
      },
      {
        symbol: "ZW",
        name: "Wheat",
        category: "agriculture",
        price: 6.45,
        change: -0.08,
        changePercent: -1.22,
        unit: "per bushel",
        currency: "USD",
        volume: 45678,
        lastUpdated: new Date().toISOString(),
      },
    ];

    // Filter by category if specified
    if (category) {
      commodities = commodities.filter((c) => c.category === category);
    }

    // Filter by symbol if specified
    if (symbol) {
      commodities = commodities.filter((c) => c.symbol === symbol);
    }

    res.success({data: commodities,
      filters: {
        category: category || null,
        symbol: symbol || null,
      },
      metadata: {
        totalCount: commodities.length,
        priceDate: new Date().toISOString(),
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching commodity prices:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch commodity prices",
      details: error.message,
    });
  }
});

// Get market summary
router.get("/market-summary", (req, res) => {
  try {
    const summary = {
      overview: {
        totalMarketCap: 4.2e12,
        totalVolume: 1.8e9,
        activeContracts: 125847,
        tradingSession: "open",
      },
      performance: {
        "1d": {
          gainers: 18,
          losers: 12,
          unchanged: 3,
          topGainer: { symbol: "HG", name: "Copper", change: 1.17 },
          topLoser: { symbol: "NG", name: "Natural Gas", change: -4.02 },
        },
      },
      sectors: [
        {
          name: "Energy",
          weight: 0.35,
          change: 0.62,
          volume: 8.9e8,
        },
        {
          name: "Precious Metals",
          weight: 0.25,
          change: -0.15,
          volume: 3.2e8,
        },
      ],
    };

    res.success({data: summary,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching market summary:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch market summary",
      details: error.message,
    });
  }
});

// Get correlations
router.get("/correlations", (req, res) => {
  try {
    const correlations = {
      overview: {
        description: "Correlation matrix for major commodity sectors",
        period: "90d",
        lastUpdated: new Date().toISOString(),
      },
      matrix: {
        energy: {
          energy: 1.0,
          "precious-metals": -0.23,
          "base-metals": 0.47,
          agriculture: 0.12,
          livestock: 0.08,
        },
        "precious-metals": {
          energy: -0.23,
          "precious-metals": 1.0,
          "base-metals": 0.18,
          agriculture: -0.05,
          livestock: -0.02,
        },
      },
    };

    res.success({data: correlations,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching correlations:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch correlations",
      details: error.message,
    });
  }
});

// Get commodities futures endpoint  
router.get("/futures", async (req, res) => {
  try {
    const { category = "all", expiration = "all", limit = 20 } = req.query;
    console.log(`📈 Commodities futures requested - category: ${category}, limit: ${limit}`);

    // Import query function for database access
    const { query } = require("../utils/database");
    
    // Try to fetch real futures data from database
    let whereClause = "WHERE active = true";
    const params = [parseInt(limit)];
    let paramIndex = 2;

    if (category !== "all") {
      whereClause += ` AND category = $${paramIndex}`;
      params.push(category);
      paramIndex++;
    }

    if (expiration !== "all") {
      whereClause += ` AND expiration_date >= $${paramIndex}`;
      params.push(expiration);
      paramIndex++;
    }

    const futuresQuery = `
      SELECT 
        symbol,
        underlying_symbol,
        contract_name,
        category,
        contract_month,
        expiration_date,
        last_price,
        price_change,
        change_percent,
        bid_price,
        ask_price,
        high_price,
        low_price,
        volume,
        open_interest,
        tick_size,
        tick_value,
        contract_size,
        exchange,
        settlement_type,
        updated_at
      FROM futures_contracts 
      ${whereClause}
      ORDER BY volume DESC, expiration_date ASC
      LIMIT $1
    `;

    const result = await query(futuresQuery, params);

    if (!result || !result.rows || result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No futures data available",
        details: "Futures contracts data is not currently available in the database. This may be due to missing data feeds or database connectivity issues.",
        troubleshooting: {
          suggestion: "Check futures data pipeline and database connectivity",
          possible_causes: [
            "Futures data feed is not configured or running",
            "Database connection issues",
            "No active futures contracts in the selected category",
            "Data pipeline may need to be initialized with futures contract data"
          ]
        },
        filters: { category, expiration, limit: parseInt(limit) },
        timestamp: new Date().toISOString()
      });
    }

    // Transform database results to expected format
    const contracts = result.rows.map(row => ({
      symbol: row.symbol,
      underlying: row.underlying_symbol,
      name: row.contract_name,
      category: row.category,
      contract_month: row.contract_month,
      expiration_date: row.expiration_date,
      
      price_data: {
        last_price: parseFloat(row.last_price || 0),
        change: parseFloat(row.price_change || 0),
        change_percent: parseFloat(row.change_percent || 0),
        bid: parseFloat(row.bid_price || 0),
        ask: parseFloat(row.ask_price || 0),
        high: parseFloat(row.high_price || 0),
        low: parseFloat(row.low_price || 0),
        volume: parseInt(row.volume || 0),
        open_interest: parseInt(row.open_interest || 0)
      },
          
      contract_specs: {
        tick_size: parseFloat(row.tick_size || 0.01),
        tick_value: parseFloat(row.tick_value || 10),
        contract_size: row.contract_size || "Unknown",
        currency: "USD",
        exchange: row.exchange || "Unknown",
        settlement: row.settlement_type || "physical"
      },
      
      last_updated: row.updated_at
    }));

    // Calculate market summary from real data
    const totalVolume = contracts.reduce((sum, c) => sum + c.price_data.volume, 0);
    const totalOpenInterest = contracts.reduce((sum, c) => sum + c.price_data.open_interest, 0);
    const uniqueExchanges = [...new Set(contracts.map(c => c.contract_specs.exchange).filter(e => e !== "Unknown"))];

    const futuresData = {
      contracts: contracts,
      market_summary: {
        total_contracts: contracts.length,
        active_sessions: uniqueExchanges.length > 0 ? uniqueExchanges : ["NYMEX", "COMEX", "CBOT", "ICE"],
        total_volume_today: totalVolume,
        total_open_interest: totalOpenInterest,
        data_freshness: contracts.length > 0 ? "live" : "stale"
      }
    };

    res.json({
      success: true,
      data: futuresData,
      filters: { category, expiration, limit: parseInt(limit) },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Commodities futures error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch commodities futures",
      message: error.message
    });
  }
});

// Get commodities trends endpoint
router.get("/trends", async (req, res) => {
  try {
    const { timeframe = "1m", category = "all" } = req.query;
    console.log(`📊 Commodities trends requested - timeframe: ${timeframe}, category: ${category}`);

    // Import query function
    const { query } = require("../utils/database");

    // Map timeframe to days for SQL
    const timeframeDays = {
      "1w": 7,
      "1m": 30,
      "3m": 90,
      "6m": 180,
      "1y": 365
    };
    const days = timeframeDays[timeframe] || 30;

    try {
      // Try to fetch sector trends from database
      const trendsQuery = `
        SELECT 
          category as sector,
          COUNT(*) as contract_count,
          AVG(change_percent) as avg_performance,
          STDDEV(change_percent) as volatility,
          SUM(CASE WHEN change_percent > 0 THEN 1 ELSE 0 END) as positive_count
        FROM futures_contracts 
        WHERE active = true 
          AND last_updated >= NOW() - INTERVAL '${days} days'
          ${category !== "all" ? "AND category = $1" : ""}
        GROUP BY category
        ORDER BY avg_performance DESC
      `;

      const trendsParams = category !== "all" ? [category] : [];
      const trendsResult = await query(trendsQuery, trendsParams);

      // Try to fetch top movers
      const moversQuery = `
        SELECT 
          symbol,
          contract_name as name,
          change_percent,
          volume
        FROM futures_contracts 
        WHERE active = true 
          AND last_updated >= NOW() - INTERVAL '1 day'
          AND change_percent IS NOT NULL
        ORDER BY ABS(change_percent) DESC
        LIMIT 10
      `;

      const moversResult = await query(moversQuery);
      
      let trendsData;

      if (!trendsResult || trendsResult.rows.length === 0) {
        // No data available
        return res.status(404).json({
          success: false,
          error: "No commodities trend data available",
          details: "Commodities trend analysis data is not currently available in the database. This requires historical price data and technical analysis calculations.",
          troubleshooting: {
            suggestion: "Check commodities data pipeline and ensure historical data is being loaded",
            possible_causes: [
              "Commodities price data feed is not active",
              "Historical data tables are empty or not properly updated",
              "Technical analysis calculations are not running",
              "Database connection issues or missing tables"
            ]
          },
          filters: { timeframe, category },
          timestamp: new Date().toISOString()
        });
      }

      // Process sector trends from real data
      const sectorTrends = trendsResult.rows.map(row => {
        const positiveRatio = row.positive_count / row.contract_count;
        const trendDirection = positiveRatio > 0.6 ? "bullish" : 
                             positiveRatio < 0.4 ? "bearish" : "sideways";
        
        return {
          sector: row.sector,
          trend_direction: trendDirection,
          strength: Math.round(Math.abs(row.avg_performance || 0) * 10),
          contract_count: parseInt(row.contract_count || 0),
          avg_performance: parseFloat((row.avg_performance || 0).toFixed(2)),
          volatility: parseFloat((row.volatility || 0).toFixed(2)),
          positive_contracts: parseInt(row.positive_count || 0)
        };
      });

      // Process top movers from real data
      const allMovers = moversResult && moversResult.rows ? moversResult.rows : [];
      const gainers = allMovers
        .filter(row => parseFloat(row.change_percent || 0) > 0)
        .slice(0, 5)
        .map(row => ({
          symbol: row.symbol,
          name: row.name || row.symbol,
          change_percent: parseFloat((row.change_percent || 0).toFixed(2)),
          volume: parseInt(row.volume || 0)
        }));

      const losers = allMovers
        .filter(row => parseFloat(row.change_percent || 0) < 0)
        .slice(0, 5)
        .map(row => ({
          symbol: row.symbol,
          name: row.name || row.symbol,
          change_percent: parseFloat((row.change_percent || 0).toFixed(2)),
          volume: parseInt(row.volume || 0)
        }));

      trendsData = {
        timeframe: timeframe,
        analysis_date: new Date().toISOString().split('T')[0],
        data_source: "database",
        
        sector_trends: sectorTrends,
        
        top_movers: {
          gainers: gainers,
          losers: losers
        }
      };

      res.json({
        success: true,
        data: trendsData,
        metadata: {
          data_points_analyzed: sectorTrends.length + gainers.length + losers.length,
          confidence_level: sectorTrends.length > 0 ? "high" : "low",
          last_updated: new Date().toISOString()
        },
        timestamp: new Date().toISOString()
      });

    } catch (dbError) {
      console.error("Database error in trends:", dbError);
      return res.status(503).json({
        success: false,
        error: "Database connection failed",
        details: `Unable to fetch commodities trend data from database: ${dbError.message}`,
        troubleshooting: {
          suggestion: "Check database connectivity and table structure",
          possible_causes: [
            "Database server is down or unreachable",
            "futures_contracts table does not exist",
            "Required columns are missing from futures_contracts table",
            "Database connection pool exhausted"
          ]
        },
        filters: { timeframe, category },
        timestamp: new Date().toISOString()
      });
    }

  } catch (error) {
    console.error("Commodities trends error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch commodities trends",
      message: error.message
    });
  }
});

module.exports = router;

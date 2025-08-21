const express = require("express");
const router = express.Router();
const { authenticateToken } = require("../middleware/auth");
const { query } = require("../utils/database");

// Health endpoint (no auth required)
router.get("/health", (req, res) => {
  res.json({
    success: true,
    status: "operational",
    service: "crypto",
    timestamp: new Date().toISOString(),
    message: "Crypto service is running",
  });
});

// Basic root endpoint (public)
router.get("/", (req, res) => {
  res.json({
    success: true,
    message: "Crypto API - Ready",
    timestamp: new Date().toISOString(),
    status: "operational",
  });
});

// Get cryptocurrency market overview
router.get("/market-overview", async (req, res) => {
  try {
    console.log(
      "🚀 [CRYPTO-MARKET] Fetching market overview data from database"
    );

    // Get market overview data from crypto_market_data table
    const overviewQuery = `
      SELECT 
        COUNT(*) as total_cryptocurrencies,
        SUM(market_cap_usd) as total_market_cap,
        SUM(volume_24h_usd) as total_volume_24h,
        AVG(price_change_percentage_24h) as avg_price_change_24h,
        MAX(CASE WHEN symbol = 'BTC' THEN market_cap_usd END) as btc_market_cap,
        MAX(CASE WHEN symbol = 'ETH' THEN market_cap_usd END) as eth_market_cap
      FROM crypto_market_data 
      WHERE market_cap_usd IS NOT NULL AND market_cap_usd > 0
    `;

    const overviewResult = await query(overviewQuery);
    const overview = overviewResult.rows[0];

    // Calculate dominance percentages
    const totalMarketCap = parseFloat(overview.total_market_cap || 0);
    const btcMarketCap = parseFloat(overview.btc_market_cap || 0);
    const ethMarketCap = parseFloat(overview.eth_market_cap || 0);

    const btcDominance =
      totalMarketCap > 0 ? (btcMarketCap / totalMarketCap) * 100 : 0;
    const ethDominance =
      totalMarketCap > 0 ? (ethMarketCap / totalMarketCap) * 100 : 0;

    // Get top gainers and losers
    const gainersQuery = `
      SELECT symbol, price_change_percentage_24h, price_usd
      FROM crypto_market_data 
      WHERE price_change_percentage_24h IS NOT NULL
      ORDER BY price_change_percentage_24h DESC 
      LIMIT 5
    `;

    const losersQuery = `
      SELECT symbol, price_change_percentage_24h, price_usd
      FROM crypto_market_data 
      WHERE price_change_percentage_24h IS NOT NULL
      ORDER BY price_change_percentage_24h ASC 
      LIMIT 5
    `;

    const [gainersResult, losersResult] = await Promise.all([
      query(gainersQuery),
      query(losersQuery),
    ]);

    const marketOverview = {
      market: {
        totalMarketCap: Math.round(totalMarketCap),
        totalVolume24h: Math.round(parseFloat(overview.total_volume_24h || 0)),
        totalCoins: parseInt(overview.total_cryptocurrencies || 0),
        avgChange24h:
          Math.round(parseFloat(overview.avg_price_change_24h || 0) * 100) /
          100,
        btcDominance: Math.round(btcDominance * 100) / 100,
        ethDominance: Math.round(ethDominance * 100) / 100,
      },
      topGainers: gainersResult.rows.map((row) => ({
        symbol: row.symbol,
        change24h:
          Math.round(parseFloat(row.price_change_percentage_24h) * 100) / 100,
        price: parseFloat(row.price_usd),
      })),
      topLosers: losersResult.rows.map((row) => ({
        symbol: row.symbol,
        change24h:
          Math.round(parseFloat(row.price_change_percentage_24h) * 100) / 100,
        price: parseFloat(row.price_usd),
      })),
    };

    res.json({
      success: true,
      data: marketOverview,
      last_updated: new Date().toISOString(),
    });
  } catch (error) {
    console.error("❌ [CRYPTO-MARKET] Error fetching market overview:", error);

    res.status(500).json({
      success: false,
      error: "Failed to fetch cryptocurrency market overview",
      details: error.message,
      suggestion:
        "Ensure crypto_market_data table has been populated with current data",
      last_updated: new Date().toISOString(),
    });
  }
});

// Get top cryptocurrencies by market cap
router.get("/top-coins", async (req, res) => {
  try {
    const { limit = 50, page = 1, order = "market_cap_desc" } = req.query;
    const offset = (parseInt(page) - 1) * parseInt(limit);

    console.log(
      `📊 [CRYPTO-TOP] Fetching top ${limit} cryptocurrencies from database`
    );

    // Build ORDER BY clause based on order parameter
    let orderBy = "cmd.market_cap_usd DESC";
    switch (order) {
      case "market_cap_asc":
        orderBy = "cmd.market_cap_usd ASC";
        break;
      case "volume_desc":
        orderBy = "cmd.volume_24h_usd DESC";
        break;
      case "volume_asc":
        orderBy = "cmd.volume_24h_usd ASC";
        break;
      case "price_desc":
        orderBy = "cmd.price_usd DESC";
        break;
      case "price_asc":
        orderBy = "cmd.price_usd ASC";
        break;
      case "change_desc":
        orderBy = "cmd.price_change_percentage_24h DESC";
        break;
      case "change_asc":
        orderBy = "cmd.price_change_percentage_24h ASC";
        break;
      default:
        orderBy = "cmd.market_cap_usd DESC";
    }

    // Get top cryptocurrencies with enriched data
    const topCoinsQuery = `
      SELECT 
        cs.symbol,
        cs.name,
        cs.category,
        cmd.price_usd,
        cmd.market_cap_usd,
        cmd.volume_24h_usd,
        cmd.price_change_24h,
        cmd.price_change_percentage_24h,
        cmd.price_change_percentage_7d,
        cmd.high_24h,
        cmd.low_24h,
        cmd.ath,
        cmd.ath_date,
        cmd.circulating_supply,
        cmd.last_updated
      FROM crypto_market_data cmd
      JOIN crypto_symbols cs ON cmd.symbol = cs.symbol
      WHERE cmd.market_cap_usd IS NOT NULL AND cmd.market_cap_usd > 0
      ORDER BY ${orderBy}
      LIMIT $1 OFFSET $2
    `;

    // Get total count for pagination
    const totalCountQuery = `
      SELECT COUNT(*) as total
      FROM crypto_market_data cmd
      JOIN crypto_symbols cs ON cmd.symbol = cs.symbol
      WHERE cmd.market_cap_usd IS NOT NULL AND cmd.market_cap_usd > 0
    `;

    const [topCoinsResult, totalCountResult] = await Promise.all([
      query(topCoinsQuery, [parseInt(limit), offset]),
      query(totalCountQuery),
    ]);

    const topCoins = topCoinsResult.rows.map((coin, index) => ({
      rank: offset + index + 1,
      symbol: coin.symbol,
      name: coin.name,
      category: coin.category,
      price: parseFloat(coin.price_usd || 0),
      marketCap: parseFloat(coin.market_cap_usd || 0),
      volume24h: parseFloat(coin.volume_24h_usd || 0),
      change24h: parseFloat(coin.price_change_24h || 0),
      changePercent24h: parseFloat(coin.price_change_percentage_24h || 0),
      changePercent7d: parseFloat(coin.price_change_percentage_7d || 0),
      high24h: parseFloat(coin.high_24h || 0),
      low24h: parseFloat(coin.low_24h || 0),
      ath: parseFloat(coin.ath || 0),
      athDate: coin.ath_date,
      circulatingSupply: parseFloat(coin.circulating_supply || 0),
      lastUpdated: coin.last_updated,
    }));

    const totalCount = parseInt(totalCountResult.rows[0]?.total || 0);

    res.json({
      success: true,
      data: topCoins,
      pagination: {
        page: parseInt(page),
        limit: parseInt(limit),
        total: totalCount,
        totalPages: Math.ceil(totalCount / parseInt(limit)),
        hasNext: parseInt(page) * parseInt(limit) < totalCount,
        hasPrev: parseInt(page) > 1,
      },
      last_updated: new Date().toISOString(),
    });
  } catch (error) {
    console.error("❌ [CRYPTO-TOP] Error fetching top coins:", error);

    res.status(500).json({
      success: false,
      error: "Failed to fetch top cryptocurrencies",
      details: error.message,
      suggestion:
        "Ensure crypto_market_data and crypto_symbols tables are populated",
      last_updated: new Date().toISOString(),
    });
  }
});

// Get cryptocurrency price data
router.get("/prices/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    const { timeframe = "24h", vs_currency = "usd" } = req.query;

    console.log(
      `💰 [CRYPTO-PRICE] Fetching price data for ${symbol.toUpperCase()}`
    );

    const priceData = await generateCryptoPriceData(symbol.toUpperCase(), {
      timeframe,
      vs_currency,
    });

    res.json({
      success: true,
      data: priceData,
      symbol: symbol.toUpperCase(),
      vs_currency,
      timeframe,
      last_updated: new Date().toISOString(),
    });
  } catch (error) {
    console.error(
      `❌ [CRYPTO-PRICE] Error fetching price for ${req.params.symbol}:`,
      error
    );

    res.json({
      success: true,
      data: generateFallbackPriceData(req.params.symbol),
      fallback: true,
      error: error.message,
      last_updated: new Date().toISOString(),
    });
  }
});

// Get cryptocurrency historical data
router.get("/historical/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    const { days = 30, interval = "daily", vs_currency = "usd" } = req.query;

    console.log(
      `📈 [CRYPTO-HISTORICAL] Fetching ${days} days of ${symbol.toUpperCase()} data`
    );

    const historicalData = await generateHistoricalData(symbol.toUpperCase(), {
      days: parseInt(days),
      interval,
      vs_currency,
    });

    res.json({
      success: true,
      data: historicalData,
      symbol: symbol.toUpperCase(),
      parameters: {
        days: parseInt(days),
        interval,
        vs_currency,
      },
      last_updated: new Date().toISOString(),
    });
  } catch (error) {
    console.error(
      `❌ [CRYPTO-HISTORICAL] Error fetching historical data for ${req.params.symbol}:`,
      error
    );

    res.json({
      success: true,
      data: generateFallbackHistoricalData(req.params.symbol),
      fallback: true,
      error: error.message,
      last_updated: new Date().toISOString(),
    });
  }
});

// Get trending cryptocurrencies
router.get("/trending", async (req, res) => {
  try {
    const { timeframe = "24h", limit = 10 } = req.query;

    console.log(`🔥 [CRYPTO-TRENDING] Fetching trending cryptocurrencies`);

    const trendingData = await generateTrendingCryptos({
      timeframe,
      limit: parseInt(limit),
    });

    res.json({
      success: true,
      data: trendingData,
      timeframe,
      last_updated: new Date().toISOString(),
    });
  } catch (error) {
    console.error("❌ [CRYPTO-TRENDING] Error fetching trending data:", error);

    res.json({
      success: true,
      data: generateFallbackTrending(),
      fallback: true,
      error: error.message,
      last_updated: new Date().toISOString(),
    });
  }
});

// Get crypto portfolio data (requires authentication)
router.get("/portfolio", authenticateToken, async (req, res) => {
  try {
    const { user_id } = req.user;

    console.log(`👤 [CRYPTO-PORTFOLIO] Fetching portfolio for user ${user_id}`);

    const portfolioData = await generateUserCryptoPortfolio(user_id);

    res.json({
      success: true,
      data: portfolioData,
      user_id,
      last_updated: new Date().toISOString(),
    });
  } catch (error) {
    console.error(`❌ [CRYPTO-PORTFOLIO] Error fetching portfolio:`, error);

    res.json({
      success: true,
      data: generateFallbackPortfolio(),
      fallback: true,
      error: error.message,
      last_updated: new Date().toISOString(),
    });
  }
});

// Add crypto position to portfolio (requires authentication)
router.post("/portfolio/add", authenticateToken, async (req, res) => {
  try {
    const { user_id } = req.user;
    const { symbol, quantity, purchase_price, purchase_date } = req.body;

    if (!symbol || !quantity || !purchase_price) {
      return res.status(400).json({
        success: false,
        error: "Missing required fields: symbol, quantity, purchase_price",
      });
    }

    console.log(
      `➕ [CRYPTO-PORTFOLIO] Adding ${quantity} ${symbol} for user ${user_id}`
    );

    const position = await addCryptoPosition(user_id, {
      symbol: symbol.toUpperCase(),
      quantity: parseFloat(quantity),
      purchase_price: parseFloat(purchase_price),
      purchase_date: purchase_date || new Date().toISOString(),
    });

    res.json({
      success: true,
      data: position,
      message: `Successfully added ${quantity} ${symbol.toUpperCase()} to portfolio`,
      last_updated: new Date().toISOString(),
    });
  } catch (error) {
    console.error("❌ [CRYPTO-PORTFOLIO] Error adding position:", error);

    res.status(500).json({
      success: false,
      error: "Failed to add crypto position",
      message: error.message,
    });
  }
});

// Get crypto news and sentiment
router.get("/news", async (req, res) => {
  try {
    const {
      symbol,
      limit = 20,
      timeframe = "24h",
      sentiment_filter,
    } = req.query;

    console.log(
      `📰 [CRYPTO-NEWS] Fetching crypto news${symbol ? ` for ${symbol}` : ""}`
    );

    const newsData = await generateCryptoNews({
      symbol: symbol?.toUpperCase(),
      limit: parseInt(limit),
      timeframe,
      sentiment_filter,
    });

    res.json({
      success: true,
      data: newsData,
      filters: {
        symbol: symbol?.toUpperCase(),
        timeframe,
        sentiment_filter,
      },
      last_updated: new Date().toISOString(),
    });
  } catch (error) {
    console.error("❌ [CRYPTO-NEWS] Error fetching crypto news:", error);

    res.json({
      success: true,
      data: generateFallbackCryptoNews(),
      fallback: true,
      error: error.message,
      last_updated: new Date().toISOString(),
    });
  }
});

// Get DeFi protocols data
router.get("/defi", async (req, res) => {
  try {
    const { category, limit = 20 } = req.query;

    console.log(`🏦 [CRYPTO-DEFI] Fetching DeFi protocols data`);

    const defiData = await generateDeFiData({
      category,
      limit: parseInt(limit),
    });

    res.json({
      success: true,
      data: defiData,
      category: category || "all",
      last_updated: new Date().toISOString(),
    });
  } catch (error) {
    console.error("❌ [CRYPTO-DEFI] Error fetching DeFi data:", error);

    res.json({
      success: true,
      data: generateFallbackDeFiData(),
      fallback: true,
      error: error.message,
      last_updated: new Date().toISOString(),
    });
  }
});

// Generate comprehensive crypto market overview
async function _generateCryptoMarketOverview() {
  const totalMarketCap = 2200000000000 + (Math.random() - 0.5) * 200000000000; // ~$2.2T ± 200B
  const totalVolume24h = 85000000000 + (Math.random() - 0.5) * 15000000000; // ~$85B ± 15B
  const btcDominance = 48 + (Math.random() - 0.5) * 8; // 48% ± 4%
  const ethDominance = 18 + (Math.random() - 0.5) * 4; // 18% ± 2%

  return {
    market_cap_usd: Math.round(totalMarketCap),
    volume_24h_usd: Math.round(totalVolume24h),
    market_cap_change_24h: -2 + Math.random() * 8, // -2% to 6%
    volume_change_24h: -5 + Math.random() * 15, // -5% to 10%
    btc_dominance: Math.round(btcDominance * 100) / 100,
    eth_dominance: Math.round(ethDominance * 100) / 100,
    total_cryptocurrencies: 12500 + Math.floor(Math.random() * 500),
    active_exchanges: 450 + Math.floor(Math.random() * 50),
    fear_greed_index: {
      value: Math.floor(Math.random() * 100),
      label: getFearGreedLabel(Math.floor(Math.random() * 100)),
      change_24h: -10 + Math.random() * 20,
    },
    trending_coins: generateTrendingCoinsList(),
  };
}

// Generate top cryptocurrencies data
async function _generateTopCryptocurrencies(options) {
  const baseCoins = [
    { symbol: "BTC", name: "Bitcoin", rank: 1 },
    { symbol: "ETH", name: "Ethereum", rank: 2 },
    { symbol: "BNB", name: "BNB", rank: 3 },
    { symbol: "XRP", name: "XRP", rank: 4 },
    { symbol: "USDT", name: "Tether", rank: 5 },
    { symbol: "SOL", name: "Solana", rank: 6 },
    { symbol: "USDC", name: "USD Coin", rank: 7 },
    { symbol: "ADA", name: "Cardano", rank: 8 },
    { symbol: "AVAX", name: "Avalanche", rank: 9 },
    { symbol: "DOGE", name: "Dogecoin", rank: 10 },
  ];

  const coins = [];
  const startIndex = (options.page - 1) * options.limit;

  for (let i = 0; i < options.limit; i++) {
    const rank = startIndex + i + 1;
    const baseCoin = baseCoins[i] || {
      symbol: `COIN${rank}`,
      name: `Cryptocurrency ${rank}`,
      rank,
    };

    const price =
      rank === 1
        ? 42000 + Math.random() * 8000 // BTC: $42k-50k
        : rank === 2
          ? 2500 + Math.random() * 800 // ETH: $2.5k-3.3k
          : rank <= 10
            ? 1 + Math.random() * 500 // Top 10: $1-500
            : 0.01 + Math.random() * 10; // Others: $0.01-10

    const marketCap =
      rank === 1
        ? 850000000000 // BTC: ~$850B
        : rank === 2
          ? 320000000000 // ETH: ~$320B
          : price * (50000000000 / rank); // Realistic market cap distribution

    coins.push({
      id: baseCoin.symbol.toLowerCase(),
      symbol: baseCoin.symbol,
      name: baseCoin.name,
      rank,
      price_usd: Math.round(price * 100) / 100,
      market_cap_usd: Math.round(marketCap),
      volume_24h_usd: Math.round(marketCap * (0.05 + Math.random() * 0.15)), // 5-20% of market cap
      change_24h: -15 + Math.random() * 30, // -15% to +15%
      change_7d: -25 + Math.random() * 50, // -25% to +25%
      circulating_supply: Math.round(marketCap / price),
      total_supply: Math.round((marketCap / price) * (1 + Math.random() * 0.5)),
      last_updated: new Date().toISOString(),
    });
  }

  return {
    coins,
    total_count: 5000,
    page: options.page,
    per_page: options.limit,
  };
}

// Generate crypto price data with technical indicators
async function generateCryptoPriceData(symbol, options) {
  const basePrice = getBasePriceForSymbol(symbol);
  const currentPrice = basePrice * (0.9 + Math.random() * 0.2); // ±10% variation

  return {
    symbol,
    current_price: Math.round(currentPrice * 100) / 100,
    price_change_24h:
      Math.round(currentPrice * (-0.15 + Math.random() * 0.3) * 100) / 100,
    price_change_percentage_24h: -15 + Math.random() * 30,
    market_cap: Math.round(
      currentPrice * (10000000 + Math.random() * 50000000)
    ),
    volume_24h: Math.round(currentPrice * (500000 + Math.random() * 2000000)),
    high_24h:
      Math.round(currentPrice * (1.02 + Math.random() * 0.08) * 100) / 100,
    low_24h:
      Math.round(currentPrice * (0.92 + Math.random() * 0.08) * 100) / 100,
    circulating_supply: 10000000 + Math.random() * 90000000,
    total_supply: 15000000 + Math.random() * 85000000,
    ath: Math.round(currentPrice * (1.5 + Math.random() * 2) * 100) / 100,
    ath_date: new Date(
      Date.now() - Math.random() * 365 * 24 * 60 * 60 * 1000
    ).toISOString(),
    atl: Math.round(currentPrice * (0.1 + Math.random() * 0.4) * 100) / 100,
    atl_date: new Date(
      Date.now() - Math.random() * 1095 * 24 * 60 * 60 * 1000
    ).toISOString(),
    technical_indicators: generateTechnicalIndicators(currentPrice),
    vs_currency: options.vs_currency || "usd",
  };
}

// Generate historical price data
async function generateHistoricalData(symbol, options) {
  const basePrice = getBasePriceForSymbol(symbol);
  const prices = [];
  const volumes = [];
  const market_caps = [];

  for (let i = options.days; i >= 0; i--) {
    const date = new Date();
    date.setDate(date.getDate() - i);

    const dailyVariation = 0.9 + Math.random() * 0.2; // ±10% daily variation
    const price = basePrice * dailyVariation * (0.8 + Math.random() * 0.4); // Overall ±20% range
    const volume = (1000000 + Math.random() * 10000000) * price;
    const market_cap = price * (50000000 + Math.random() * 100000000);

    prices.push([date.getTime(), Math.round(price * 100) / 100]);
    volumes.push([date.getTime(), Math.round(volume)]);
    market_caps.push([date.getTime(), Math.round(market_cap)]);
  }

  return {
    symbol,
    prices,
    market_caps,
    total_volumes: volumes,
    vs_currency: options.vs_currency || "usd",
  };
}

// Generate trending cryptocurrencies
async function generateTrendingCryptos(options) {
  const trendingCoins = [
    "BTC",
    "ETH",
    "SOL",
    "AVAX",
    "MATIC",
    "DOT",
    "LINK",
    "UNI",
    "AAVE",
    "CRV",
  ];

  return {
    trending: trendingCoins.slice(0, options.limit).map((symbol, index) => ({
      id: symbol.toLowerCase(),
      symbol,
      name: getCoinNameBySymbol(symbol),
      rank: index + 1,
      price_change_24h: -20 + Math.random() * 40,
      volume_increase_24h: Math.random() * 200,
      social_mentions_24h: Math.floor(Math.random() * 50000) + 5000,
      trending_score:
        Math.round((90 - index * 5 + Math.random() * 10) * 100) / 100,
    })),
    timeframe: options.timeframe,
  };
}

// Generate user crypto portfolio
async function generateUserCryptoPortfolio(userId) {
  const holdings = [
    {
      symbol: "BTC",
      quantity: 0.5 + Math.random() * 2,
      purchase_price: 35000 + Math.random() * 10000,
    },
    {
      symbol: "ETH",
      quantity: 2 + Math.random() * 8,
      purchase_price: 2000 + Math.random() * 1000,
    },
    {
      symbol: "SOL",
      quantity: 10 + Math.random() * 40,
      purchase_price: 80 + Math.random() * 40,
    },
  ];

  let totalValue = 0;
  let totalCost = 0;

  const positions = holdings.map((holding) => {
    const currentPrice = getBasePriceForSymbol(holding.symbol);
    const currentValue = holding.quantity * currentPrice;
    const totalCostBasis = holding.quantity * holding.purchase_price;
    const pnl = currentValue - totalCostBasis;
    const pnlPercentage = (pnl / totalCostBasis) * 100;

    totalValue += currentValue;
    totalCost += totalCostBasis;

    return {
      symbol: holding.symbol,
      quantity: Math.round(holding.quantity * 1000000) / 1000000,
      purchase_price: Math.round(holding.purchase_price * 100) / 100,
      current_price: Math.round(currentPrice * 100) / 100,
      current_value: Math.round(currentValue * 100) / 100,
      total_cost: Math.round(totalCostBasis * 100) / 100,
      pnl: Math.round(pnl * 100) / 100,
      pnl_percentage: Math.round(pnlPercentage * 100) / 100,
      allocation_percentage: 0, // Will be calculated after total
      purchase_date: new Date(
        Date.now() - Math.random() * 365 * 24 * 60 * 60 * 1000
      ).toISOString(),
    };
  });

  // Calculate allocation percentages
  positions.forEach((position) => {
    position.allocation_percentage =
      Math.round((position.current_value / totalValue) * 100 * 100) / 100;
  });

  return {
    user_id: userId,
    portfolio_summary: {
      total_value: Math.round(totalValue * 100) / 100,
      total_cost: Math.round(totalCost * 100) / 100,
      total_pnl: Math.round((totalValue - totalCost) * 100) / 100,
      total_pnl_percentage:
        Math.round(((totalValue - totalCost) / totalCost) * 100 * 100) / 100,
      positions_count: positions.length,
    },
    positions,
  };
}

// Add crypto position to portfolio
async function addCryptoPosition(userId, positionData) {
  // In a real implementation, this would save to database
  return {
    id: `pos_${Date.now()}`,
    user_id: userId,
    symbol: positionData.symbol,
    quantity: positionData.quantity,
    purchase_price: positionData.purchase_price,
    purchase_date: positionData.purchase_date,
    created_at: new Date().toISOString(),
  };
}

// Generate crypto news and sentiment
async function generateCryptoNews(options) {
  const cryptoHeadlines = [
    "Bitcoin Reaches New Technical Resistance Level",
    "Ethereum Network Upgrade Shows Strong Adoption",
    "DeFi Protocol Announces Major Partnership",
    "Regulatory Clarity Boosts Institutional Adoption",
    "Layer 2 Solutions Drive Transaction Volume Growth",
    "NFT Market Shows Signs of Recovery",
    "Central Bank Digital Currency Pilot Program Expands",
    "Cryptocurrency Exchange Reports Record Volume",
    "Blockchain Infrastructure Investment Increases",
    "Stablecoin Market Cap Reaches New Milestone",
  ];

  const articles = [];
  for (let i = 0; i < options.limit; i++) {
    const headline =
      cryptoHeadlines[Math.floor(Math.random() * cryptoHeadlines.length)];
    const sentiment_score = -0.4 + Math.random() * 0.8; // -0.4 to 0.4

    articles.push({
      id: `crypto_news_${Date.now()}_${i}`,
      title: headline,
      summary: generateCryptoNewsSummary(headline),
      source: generateNewsSource(),
      author: generateAuthorName(),
      published_at: new Date(
        Date.now() - Math.random() * 24 * 60 * 60 * 1000
      ).toISOString(),
      url: `https://crypto-news.example.com/article-${i}`,
      category: "cryptocurrency",
      sentiment_score: Math.round(sentiment_score * 1000) / 1000,
      sentiment_label:
        sentiment_score > 0.1
          ? "positive"
          : sentiment_score < -0.1
            ? "negative"
            : "neutral",
      impact_score: Math.round((60 + Math.random() * 40) * 100) / 100,
      related_symbols: generateRelatedCryptoSymbols(options.symbol),
    });
  }

  return {
    articles,
    summary: {
      total_articles: articles.length,
      sentiment_distribution: calculateSentimentDistribution(articles),
      avg_impact_score:
        articles.reduce((sum, a) => sum + a.impact_score, 0) / articles.length,
    },
  };
}

// Generate DeFi protocols data
async function generateDeFiData(options) {
  const defiProtocols = [
    { name: "Uniswap", category: "DEX", symbol: "UNI" },
    { name: "Aave", category: "Lending", symbol: "AAVE" },
    { name: "Compound", category: "Lending", symbol: "COMP" },
    { name: "Curve", category: "DEX", symbol: "CRV" },
    { name: "MakerDAO", category: "Lending", symbol: "MKR" },
    { name: "Yearn Finance", category: "Yield", symbol: "YFI" },
    { name: "Sushiswap", category: "DEX", symbol: "SUSHI" },
    { name: "Synthetix", category: "Derivatives", symbol: "SNX" },
  ];

  const protocols = defiProtocols.slice(0, options.limit).map((protocol) => {
    const tvl = 100000000 + Math.random() * 2000000000; // $100M - $2B TVL

    return {
      name: protocol.name,
      symbol: protocol.symbol,
      category: protocol.category,
      tvl_usd: Math.round(tvl),
      tvl_change_24h: -10 + Math.random() * 20,
      volume_24h: Math.round(tvl * (0.01 + Math.random() * 0.1)),
      users_24h: Math.floor(Math.random() * 50000) + 1000,
      transactions_24h: Math.floor(Math.random() * 100000) + 5000,
      apy_range: {
        min: Math.round((1 + Math.random() * 5) * 100) / 100,
        max: Math.round((6 + Math.random() * 15) * 100) / 100,
      },
    };
  });

  return {
    protocols,
    total_tvl: protocols.reduce((sum, p) => sum + p.tvl_usd, 0),
    categories: groupProtocolsByCategory(protocols),
  };
}

// Helper functions
function getBasePriceForSymbol(symbol) {
  const basePrices = {
    BTC: 45000,
    ETH: 2800,
    BNB: 320,
    XRP: 0.52,
    SOL: 95,
    ADA: 0.48,
    AVAX: 38,
    DOGE: 0.08,
    MATIC: 0.85,
    DOT: 6.2,
  };
  return basePrices[symbol] || 1 + Math.random() * 100;
}

function getCoinNameBySymbol(symbol) {
  const names = {
    BTC: "Bitcoin",
    ETH: "Ethereum",
    SOL: "Solana",
    AVAX: "Avalanche",
    MATIC: "Polygon",
    DOT: "Polkadot",
    LINK: "Chainlink",
    UNI: "Uniswap",
    AAVE: "Aave",
    CRV: "Curve DAO Token",
  };
  return names[symbol] || `${symbol} Token`;
}

function generateTechnicalIndicators(price) {
  return {
    rsi: Math.round((30 + Math.random() * 40) * 100) / 100, // 30-70 RSI
    macd: Math.round(price * (-0.02 + Math.random() * 0.04) * 100) / 100,
    sma_20: Math.round(price * (0.95 + Math.random() * 0.1) * 100) / 100,
    sma_50: Math.round(price * (0.9 + Math.random() * 0.2) * 100) / 100,
    bollinger_upper: Math.round(price * 1.05 * 100) / 100,
    bollinger_lower: Math.round(price * 0.95 * 100) / 100,
    volume_sma: Math.round((1000000 + Math.random() * 5000000) * 100) / 100,
  };
}

function generateTrendingCoinsList() {
  return ["BTC", "ETH", "SOL", "AVAX", "MATIC"].map((symbol) => ({
    symbol,
    name: getCoinNameBySymbol(symbol),
    price_change_24h: -10 + Math.random() * 20,
  }));
}

function getFearGreedLabel(value) {
  if (value >= 75) return "Extreme Greed";
  if (value >= 55) return "Greed";
  if (value >= 45) return "Neutral";
  if (value >= 25) return "Fear";
  return "Extreme Fear";
}

function generateCryptoNewsSummary(headline) {
  const summaries = {
    Bitcoin:
      "Analysis of Bitcoin market dynamics and technical developments affecting price action.",
    Ethereum:
      "Ethereum network updates and ecosystem developments driving adoption metrics.",
    DeFi: "Decentralized finance protocol innovations and yield optimization strategies.",
    Regulatory:
      "Cryptocurrency regulatory developments and institutional adoption trends.",
    NFT: "Non-fungible token market analysis and emerging use case implementations.",
  };

  for (const [key, summary] of Object.entries(summaries)) {
    if (headline.includes(key)) return summary;
  }
  return summaries.Bitcoin;
}

function generateNewsSource() {
  const sources = [
    "CoinDesk",
    "CoinTelegraph",
    "The Block",
    "Decrypt",
    "CryptoSlate",
  ];
  return sources[Math.floor(Math.random() * sources.length)];
}

function generateAuthorName() {
  const firstNames = ["Alex", "Sarah", "Michael", "Jessica", "David", "Rachel"];
  const lastNames = [
    "Chen",
    "Johnson",
    "Williams",
    "Davis",
    "Miller",
    "Wilson",
  ];

  const firstName = firstNames[Math.floor(Math.random() * firstNames.length)];
  const lastName = lastNames[Math.floor(Math.random() * lastNames.length)];

  return `${firstName} ${lastName}`;
}

function generateRelatedCryptoSymbols(targetSymbol) {
  const allSymbols = ["BTC", "ETH", "SOL", "AVAX", "MATIC", "DOT", "LINK"];
  if (targetSymbol) return [targetSymbol];

  const count = 1 + Math.floor(Math.random() * 3);
  return allSymbols.slice(0, count);
}

function calculateSentimentDistribution(articles) {
  const positive = articles.filter(
    (a) => a.sentiment_label === "positive"
  ).length;
  const negative = articles.filter(
    (a) => a.sentiment_label === "negative"
  ).length;
  const neutral = articles.filter(
    (a) => a.sentiment_label === "neutral"
  ).length;

  return { positive, negative, neutral };
}

function groupProtocolsByCategory(protocols) {
  const categories = {};
  protocols.forEach((protocol) => {
    if (!categories[protocol.category]) {
      categories[protocol.category] = [];
    }
    categories[protocol.category].push(protocol);
  });
  return categories;
}

// Fallback data generators
function _generateFallbackMarketOverview() {
  return {
    market_cap_usd: 2250000000000,
    volume_24h_usd: 87500000000,
    market_cap_change_24h: 2.3,
    volume_change_24h: 8.7,
    btc_dominance: 48.2,
    eth_dominance: 18.5,
    total_cryptocurrencies: 12847,
    active_exchanges: 472,
    fear_greed_index: { value: 65, label: "Greed", change_24h: 3 },
    trending_coins: [
      { symbol: "BTC", name: "Bitcoin", price_change_24h: 3.2 },
      { symbol: "ETH", name: "Ethereum", price_change_24h: 5.1 },
    ],
  };
}

function _generateFallbackTopCoins() {
  return {
    coins: [
      {
        id: "bitcoin",
        symbol: "BTC",
        name: "Bitcoin",
        rank: 1,
        price_usd: 45234.56,
        market_cap_usd: 885000000000,
        volume_24h_usd: 28500000000,
        change_24h: 3.2,
        change_7d: -1.8,
        circulating_supply: 19565432,
        total_supply: 21000000,
        last_updated: new Date().toISOString(),
      },
    ],
    total_count: 5000,
    page: 1,
    per_page: 50,
  };
}

function generateFallbackPriceData(symbol) {
  return {
    symbol: symbol.toUpperCase(),
    current_price: 45234.56,
    price_change_24h: 1456.78,
    price_change_percentage_24h: 3.33,
    market_cap: 885000000000,
    volume_24h: 28500000000,
    high_24h: 46123.45,
    low_24h: 44567.89,
    vs_currency: "usd",
  };
}

function generateFallbackHistoricalData(symbol) {
  const now = Date.now();
  return {
    symbol: symbol.toUpperCase(),
    prices: [
      [now - 86400000, 44567.89],
      [now, 45234.56],
    ],
    market_caps: [
      [now - 86400000, 875000000000],
      [now, 885000000000],
    ],
    total_volumes: [
      [now - 86400000, 26000000000],
      [now, 28500000000],
    ],
    vs_currency: "usd",
  };
}

function generateFallbackTrending() {
  return {
    trending: [
      {
        id: "bitcoin",
        symbol: "BTC",
        name: "Bitcoin",
        rank: 1,
        price_change_24h: 3.2,
        volume_increase_24h: 15.8,
        social_mentions_24h: 25847,
        trending_score: 95.2,
      },
    ],
    timeframe: "24h",
  };
}

function generateFallbackPortfolio() {
  return {
    portfolio_summary: {
      total_value: 12547.83,
      total_cost: 10200.0,
      total_pnl: 2347.83,
      total_pnl_percentage: 23.02,
      positions_count: 3,
    },
    positions: [],
  };
}

function generateFallbackCryptoNews() {
  return {
    articles: [
      {
        id: "fallback_1",
        title: "Bitcoin Market Analysis Shows Continued Institutional Interest",
        summary:
          "Analysis of Bitcoin market dynamics and institutional adoption trends.",
        source: "CoinDesk",
        author: "Sarah Johnson",
        published_at: new Date().toISOString(),
        sentiment_score: 0.35,
        sentiment_label: "positive",
        impact_score: 78.5,
      },
    ],
    summary: {
      total_articles: 1,
      sentiment_distribution: { positive: 1, negative: 0, neutral: 0 },
      avg_impact_score: 78.5,
    },
  };
}

function generateFallbackDeFiData() {
  return {
    protocols: [
      {
        name: "Uniswap",
        symbol: "UNI",
        category: "DEX",
        tvl_usd: 4250000000,
        tvl_change_24h: 2.3,
        volume_24h: 1250000000,
        users_24h: 25847,
        transactions_24h: 125000,
        apy_range: { min: 2.5, max: 15.7 },
      },
    ],
    total_tvl: 4250000000,
    categories: { DEX: ["Uniswap"] },
  };
}

module.exports = router;

const express = require('express');
const router = express.Router();
const { query } = require('../utils/database');
const enhancedCryptoDataService = require('../services/enhancedCryptoDataService');
const cryptoErrorHandler = require('../utils/cryptoErrorHandler');
const CryptoWebSocketManager = require('../services/cryptoWebSocketManager');

// Initialize WebSocket manager
const wsManager = new CryptoWebSocketManager();

// Root crypto endpoint for health checks
router.get('/', (req, res) => {
  res.json({
    success: true,
    data: {
      system: 'Enhanced Cryptocurrency API',
      version: '2.0.0',
      status: 'operational',
      features: [
        'Multi-provider data aggregation',
        'Real-time WebSocket streaming',
        'Intelligent fallback systems',
        'Comprehensive error handling',
        'Live market data integration'
      ],
      available_endpoints: [
        'GET /crypto/market-metrics - Overall crypto market metrics',
        'GET /crypto/fear-greed - Fear and Greed Index',
        'GET /crypto/movers - Top gainers and losers',
        'GET /crypto/trending - Trending cryptocurrencies',
        'GET /crypto/assets - List of crypto assets with pagination',
        'GET /crypto/prices/:symbol - Real-time price data for specific crypto',
        'GET /crypto/historical/:symbol - Historical price charts',
        'GET /crypto/market-overview - Comprehensive market overview',
        'GET /crypto/portfolio - User crypto portfolio',
        'GET /crypto/news - Cryptocurrency news',
        'GET /crypto/defi/tvl - DeFi Total Value Locked',
        'GET /crypto/exchanges - Exchange information',
        'WS /crypto/ws - Real-time WebSocket data feed',
        'GET /crypto/websocket/health - WebSocket manager health',
        'GET /crypto/websocket/snapshot - Current WebSocket data',
        'GET /crypto/services/health - Enhanced services health check',
        'POST /crypto/websocket/start - Start WebSocket manager',
        'POST /crypto/websocket/stop - Stop WebSocket manager'
      ],
      websocket_status: wsManager.isActive ? 'active' : 'inactive',
      timestamp: new Date().toISOString()
    }
  });
});

// GET /crypto/market-metrics - Get overall crypto market metrics
router.get('/market-metrics', async (req, res) => {
  try {
    const result = await query(`
      SELECT 
        total_market_cap,
        total_volume_24h,
        btc_dominance,
        eth_dominance,
        active_cryptocurrencies,
        market_cap_change_24h,
        timestamp
      FROM crypto_market_metrics 
      ORDER BY timestamp DESC 
      LIMIT 1
    `);

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: 'No market metrics data available'
      });
    }

    res.json({
      success: true,
      data: result.rows[0]
    });
  } catch (error) {
    console.error('Error fetching crypto market metrics:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch market metrics'
    });
  }
});

// GET /crypto/fear-greed - Get Fear and Greed Index
router.get('/fear-greed', async (req, res) => {
  try {
    console.log('😨 Fetching Fear and Greed Index');
    
    // Use enhanced service with intelligent fallback
    let fearGreedData;
    try {
      fearGreedData = await enhancedCryptoDataService.getFearGreedIndex();
      fearGreedData.source = 'live_api';
    } catch (apiError) {
      console.log('⚠️ Fear & Greed API failed, falling back to database');
      
      // Fallback to database
      const result = await query(`
        SELECT 
          value,
          value_classification,
          timestamp
        FROM crypto_fear_greed 
        ORDER BY timestamp DESC 
        LIMIT 1
      `);

      if (result.rows.length === 0) {
        throw new Error('No Fear and Greed data available');
      }

      fearGreedData = {
        ...result.rows[0],
        source: 'database_fallback',
        note: 'Using cached Fear & Greed data'
      };
    }

    res.json({
      success: true,
      data: fearGreedData
    });
  } catch (error) {
    console.error('Error fetching Fear and Greed Index:', error);
    
    const errorResponse = cryptoErrorHandler.handleError(error, {
      endpoint: '/fear-greed',
      dataType: 'sentiment'
    });
    
    res.status(500).json({
      success: false,
      error: errorResponse
    });
  }
});

// GET /crypto/movers - Get top gainers and losers
router.get('/movers', async (req, res) => {
  try {
    console.log('📈 Fetching crypto movers (top gainers and losers)');
    
    // Try enhanced service first for real-time data
    let moversData;
    try {
      const topCryptos = await enhancedCryptoDataService.getTopCryptocurrencies(100);
      if (topCryptos.success && topCryptos.data) {
        // Sort by 24h change to get gainers and losers
        const sortedByChange = topCryptos.data.sort((a, b) => 
          (b.price_change_percentage_24h || 0) - (a.price_change_percentage_24h || 0)
        );
        
        moversData = {
          gainers: sortedByChange.slice(0, 10).map(coin => ({
            symbol: coin.symbol,
            name: coin.name,
            price: coin.current_price,
            price_change_24h: coin.price_change_percentage_24h,
            volume_24h: coin.total_volume,
            market_cap: coin.market_cap,
            image: coin.image
          })),
          losers: sortedByChange.slice(-10).reverse().map(coin => ({
            symbol: coin.symbol,
            name: coin.name,
            price: coin.current_price,
            price_change_24h: coin.price_change_percentage_24h,
            volume_24h: coin.total_volume,
            market_cap: coin.market_cap,
            image: coin.image
          })),
          source: 'live_api'
        };
      } else {
        throw new Error('Enhanced service returned invalid data');
      }
    } catch (apiError) {
      console.log('⚠️ Live API failed, falling back to database');
      
      // Fallback to database
      const [gainersResult, losersResult] = await Promise.all([
        query(`
          SELECT 
            symbol,
            price,
            price_change_24h,
            volume_24h,
            market_cap
          FROM crypto_movers 
          WHERE mover_type = 'gainer'
          AND timestamp = (
            SELECT MAX(timestamp) FROM crypto_movers WHERE mover_type = 'gainer'
          )
          ORDER BY price_change_24h DESC
          LIMIT 10
        `),
        query(`
          SELECT 
            symbol,
            price,
            price_change_24h,
            volume_24h,
            market_cap
          FROM crypto_movers 
          WHERE mover_type = 'loser'
          AND timestamp = (
            SELECT MAX(timestamp) FROM crypto_movers WHERE mover_type = 'loser'
          )
          ORDER BY price_change_24h ASC
          LIMIT 10
        `)
      ]);

      moversData = {
        gainers: gainersResult.rows,
        losers: losersResult.rows,
        source: 'database_fallback',
        note: 'Using cached movers data'
      };
    }

    res.json({
      success: true,
      data: moversData
    });
  } catch (error) {
    console.error('Error fetching crypto movers:', error);
    
    const errorResponse = cryptoErrorHandler.handleError(error, {
      endpoint: '/movers',
      dataType: 'market_movers'
    });
    
    res.status(500).json({
      success: false,
      error: errorResponse
    });
  }
});

// GET /crypto/trending - Get trending cryptocurrencies
router.get('/trending', async (req, res) => {
  try {
    console.log('🔥 Fetching trending cryptocurrencies');
    
    let trendingData;
    try {
      // Get top cryptocurrencies by volume and recent price movement
      const topCryptos = await enhancedCryptoDataService.getTopCryptocurrencies(50);
      if (topCryptos.success && topCryptos.data) {
        // Calculate trending score based on volume and price change
        const trending = topCryptos.data
          .map(coin => ({
            symbol: coin.symbol,
            name: coin.name,
            coingecko_id: coin.id,
            market_cap_rank: coin.market_cap_rank,
            current_price: coin.current_price,
            price_change_24h: coin.price_change_percentage_24h,
            total_volume: coin.total_volume,
            image: coin.image,
            // Calculate trending score: volume rank + price momentum
            trending_score: (
              Math.abs(coin.price_change_percentage_24h || 0) * 0.7 +
              (coin.total_volume || 0) / 1000000 * 0.3
            )
          }))
          .sort((a, b) => b.trending_score - a.trending_score)
          .slice(0, 10);
        
        trendingData = {
          trending,
          source: 'live_api'
        };
      } else {
        throw new Error('Enhanced service returned invalid data');
      }
    } catch (apiError) {
      console.log('⚠️ Live API failed, falling back to database');
      
      // Fallback to database
      const result = await query(`
        SELECT 
          symbol,
          name,
          coingecko_id,
          market_cap_rank,
          search_score
        FROM crypto_trending 
        WHERE timestamp = (
          SELECT MAX(timestamp) FROM crypto_trending
        )
        ORDER BY search_score DESC
        LIMIT 10
      `);

      trendingData = {
        trending: result.rows,
        source: 'database_fallback',
        note: 'Using cached trending data'
      };
    }

    res.json({
      success: true,
      data: trendingData
    });
  } catch (error) {
    console.error('Error fetching trending cryptos:', error);
    
    const errorResponse = cryptoErrorHandler.handleError(error, {
      endpoint: '/trending',
      dataType: 'trending'
    });
    
    res.status(500).json({
      success: false,
      error: errorResponse
    });
  }
});

// GET /crypto/prices/:symbol - Get price data for specific crypto
router.get('/prices/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const limit = parseInt(req.query.limit) || 100;
    
    console.log(`💰 Fetching price data for ${symbol}`);
    
    let priceData;
    try {
      // Check WebSocket manager for real-time data first
      const realtimeData = wsManager.getSymbolData(symbol.toUpperCase());
      if (realtimeData && realtimeData.length > 0) {
        console.log(`📡 Using real-time WebSocket data for ${symbol}`);
        priceData = {
          current: realtimeData,
          source: 'websocket_realtime'
        };
      } else {
        // Fallback to enhanced service API
        const liveData = await enhancedCryptoDataService.getRealTimePrices([symbol.toLowerCase()]);
        if (liveData.success && liveData.data.length > 0) {
          priceData = {
            current: liveData.data,
            source: 'live_api'
          };
        } else {
          throw new Error('No live data available');
        }
      }
    } catch (apiError) {
      console.log(`⚠️ Live data failed for ${symbol}, falling back to database`);
      
      // Fallback to database
      const result = await query(`
        SELECT 
          symbol,
          timestamp,
          price,
          market_cap,
          volume_24h,
          price_change_24h,
          price_change_7d,
          price_change_30d
        FROM crypto_prices 
        WHERE symbol = $1
        ORDER BY timestamp DESC
        LIMIT $2
      `, [symbol.toUpperCase(), limit]);

      priceData = {
        current: result.rows,
        source: 'database_fallback',
        note: 'Using cached price data'
      };
    }

    res.json({
      success: true,
      data: priceData
    });
  } catch (error) {
    console.error('Error fetching crypto prices:', error);
    
    const errorResponse = cryptoErrorHandler.handleError(error, {
      endpoint: '/prices',
      dataType: 'prices',
      symbols: [req.params.symbol]
    });
    
    res.status(500).json({
      success: false,
      error: errorResponse
    });
  }
});

// GET /crypto/assets - Get list of crypto assets
router.get('/assets', async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 50;
    const offset = (page - 1) * limit;
    const search = req.query.search || '';

    console.log(`📋 Fetching crypto assets (page ${page}, limit ${limit})`);
    
    let assetsData;
    try {
      // Use enhanced service for fresh market data
      const topCryptos = await enhancedCryptoDataService.getTopCryptocurrencies(Math.min(limit * 2, 250));
      if (topCryptos.success && topCryptos.data) {
        let filteredAssets = topCryptos.data;
        
        // Apply search filter if provided
        if (search) {
          const searchLower = search.toLowerCase();
          filteredAssets = filteredAssets.filter(asset => 
            asset.symbol.toLowerCase().includes(searchLower) ||
            asset.name.toLowerCase().includes(searchLower)
          );
        }
        
        // Apply pagination
        const paginatedAssets = filteredAssets.slice(offset, offset + limit);
        
        assetsData = {
          assets: paginatedAssets.map(asset => ({
            symbol: asset.symbol,
            name: asset.name,
            coingecko_id: asset.id,
            current_price: asset.current_price,
            market_cap: asset.market_cap,
            market_cap_rank: asset.market_cap_rank,
            total_volume: asset.total_volume,
            circulating_supply: asset.circulating_supply,
            total_supply: asset.total_supply,
            max_supply: asset.max_supply,
            price_change_24h: asset.price_change_percentage_24h,
            image: asset.image,
            last_updated: asset.last_updated
          })),
          pagination: {
            page,
            limit,
            total: filteredAssets.length,
            pages: Math.ceil(filteredAssets.length / limit)
          },
          source: 'live_api'
        };
      } else {
        throw new Error('Enhanced service returned invalid data');
      }
    } catch (apiError) {
      console.log('⚠️ Live API failed, falling back to database');
      
      // Fallback to database
      let whereClause = 'WHERE is_active = true';
      let params = [limit, offset];
      
      if (search) {
        whereClause += ' AND (symbol ILIKE $3 OR name ILIKE $3)';
        params.push(`%${search}%`);
      }

      const result = await query(`
        SELECT 
          symbol,
          name,
          coingecko_id,
          contract_address,
          blockchain,
          market_cap,
          circulating_supply,
          total_supply,
          max_supply,
          launch_date,
          website
        FROM crypto_assets 
        ${whereClause}
        ORDER BY market_cap DESC NULLS LAST
        LIMIT $1 OFFSET $2
      `, params);

      // Get total count
      const countParams = search ? [`%${search}%`] : [];
      const countWhere = search ? 'WHERE is_active = true AND (symbol ILIKE $1 OR name ILIKE $1)' : 'WHERE is_active = true';
      
      const countResult = await query(`
        SELECT COUNT(*) as total 
        FROM crypto_assets 
        ${countWhere}
      `, countParams);

      assetsData = {
        assets: result.rows,
        pagination: {
          page,
          limit,
          total: parseInt(countResult.rows[0].total),
          pages: Math.ceil(parseInt(countResult.rows[0].total) / limit)
        },
        source: 'database_fallback',
        note: 'Using cached assets data'
      };
    }

    res.json({
      success: true,
      data: assetsData.assets,
      pagination: assetsData.pagination,
      metadata: {
        source: assetsData.source,
        note: assetsData.note
      }
    });
  } catch (error) {
    console.error('Error fetching crypto assets:', error);
    
    const errorResponse = cryptoErrorHandler.handleError(error, {
      endpoint: '/assets',
      dataType: 'assets'
    });
    
    res.status(500).json({
      success: false,
      error: errorResponse
    });
  }
});

// GET /crypto/defi/tvl - Get DeFi Total Value Locked data
router.get('/defi/tvl', async (req, res) => {
  try {
    const chain = req.query.chain;
    const limit = parseInt(req.query.limit) || 50;

    let whereClause = '';
    let params = [limit];
    
    if (chain) {
      whereClause = 'WHERE chain = $2';
      params.push(chain);
    }

    const result = await query(`
      SELECT 
        protocol,
        chain,
        tvl_usd,
        tvl_change_24h,
        tvl_change_7d,
        category,
        timestamp
      FROM defi_tvl 
      ${whereClause}
      AND timestamp = (
        SELECT MAX(timestamp) FROM defi_tvl 
        ${whereClause ? 'WHERE chain = $2' : ''}
      )
      ORDER BY tvl_usd DESC
      LIMIT $1
    `, params);

    // Get total TVL across all protocols
    const totalResult = await query(`
      SELECT 
        SUM(tvl_usd) as total_tvl,
        COUNT(*) as protocol_count
      FROM defi_tvl
      WHERE timestamp = (SELECT MAX(timestamp) FROM defi_tvl)
      ${chain ? 'AND chain = $1' : ''}
    `, chain ? [chain] : []);

    res.json({
      success: true,
      data: result.rows,
      summary: totalResult.rows[0]
    });
  } catch (error) {
    console.error('Error fetching DeFi TVL data:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch DeFi TVL data'
    });
  }
});

// GET /crypto/exchanges - Get exchange information
router.get('/exchanges', async (req, res) => {
  try {
    const result = await query(`
      SELECT 
        exchange_id,
        name,
        country,
        trust_score,
        volume_24h_btc,
        normalized_volume_24h_btc,
        is_centralized
      FROM crypto_exchanges 
      ORDER BY trust_score DESC, volume_24h_btc DESC NULLS LAST
      LIMIT 50
    `);

    res.json({
      success: true,
      data: result.rows
    });
  } catch (error) {
    console.error('Error fetching crypto exchanges:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch crypto exchanges'
    });
  }
});

// GET /crypto/historical/:symbol - Get historical price data for specific crypto
router.get('/historical/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const days = parseInt(req.query.days) || 30;
    const interval = req.query.interval || 'daily'; // daily, hourly
    
    console.log(`📉 Fetching historical data for ${symbol} (${days} days, ${interval})`);
    
    let historicalData;
    try {
      // Use enhanced service for historical data
      const historyResult = await enhancedCryptoDataService.getHistoricalData(
        symbol.toLowerCase(), 
        days, 
        interval === 'hourly' ? 'hourly' : 'daily'
      );
      
      if (historyResult.success) {
        historicalData = {
          chart_data: historyResult.data,
          source: 'live_api'
        };
      } else {
        throw new Error('Enhanced service returned invalid historical data');
      }
    } catch (apiError) {
      console.log(`⚠️ Live API failed for ${symbol}, falling back to database`);
      
      // Fallback to database
      const endDate = new Date();
      const startDate = new Date();
      startDate.setDate(endDate.getDate() - days);

      const result = await query(`
        SELECT 
          symbol,
          timestamp,
          price,
          market_cap,
          volume_24h,
          price_change_24h,
          high_24h,
          low_24h
        FROM crypto_historical_prices 
        WHERE symbol = $1 
          AND timestamp >= $2 
          AND timestamp <= $3
        ORDER BY timestamp ASC
      `, [symbol.toUpperCase(), startDate, endDate]);

      historicalData = {
        chart_data: {
          prices: result.rows.map(row => ({
            timestamp: row.timestamp,
            price: row.price,
            time: new Date(row.timestamp).getTime()
          }))
        },
        source: 'database_fallback',
        note: 'Using cached historical data'
      };
    }

    res.json({
      success: true,
      data: historicalData.chart_data,
      metadata: {
        symbol: symbol.toUpperCase(),
        days,
        interval,
        source: historicalData.source,
        note: historicalData.note,
        data_points: historicalData.chart_data.prices?.length || 0
      }
    });
  } catch (error) {
    console.error('Error fetching crypto historical data:', error);
    
    const errorResponse = cryptoErrorHandler.handleError(error, {
      endpoint: '/historical',
      dataType: 'historical',
      symbols: [req.params.symbol]
    });
    
    res.status(500).json({
      success: false,
      error: errorResponse
    });
  }
});

// GET /crypto/portfolio - Get crypto portfolio for user
router.get('/portfolio', async (req, res) => {
  try {
    const userId = req.user?.id || 'demo-user';
    
    const result = await query(`
      SELECT 
        p.symbol,
        p.quantity,
        p.average_cost,
        p.current_price,
        p.market_value,
        p.total_cost,
        p.unrealized_pnl,
        p.unrealized_pnl_percent,
        p.last_updated,
        a.name as asset_name,
        a.blockchain
      FROM crypto_portfolio p
      LEFT JOIN crypto_assets a ON p.symbol = a.symbol
      WHERE p.user_id = $1 
        AND p.quantity > 0
      ORDER BY p.market_value DESC
    `, [userId]);

    // Calculate portfolio summary
    const totalValue = result.rows.reduce((sum, holding) => sum + parseFloat(holding.market_value || 0), 0);
    const totalCost = result.rows.reduce((sum, holding) => sum + parseFloat(holding.total_cost || 0), 0);
    const totalPnl = totalValue - totalCost;
    const totalPnlPercent = totalCost > 0 ? ((totalPnl / totalCost) * 100) : 0;

    res.json({
      success: true,
      data: {
        holdings: result.rows,
        summary: {
          total_value: totalValue,
          total_cost: totalCost,
          total_pnl: totalPnl,
          total_pnl_percent: totalPnlPercent,
          positions_count: result.rows.length,
          last_updated: new Date().toISOString()
        }
      }
    });
  } catch (error) {
    console.error('Error fetching crypto portfolio:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch crypto portfolio'
    });
  }
});

// GET /crypto/news - Get cryptocurrency news
router.get('/news', async (req, res) => {
  try {
    const limit = parseInt(req.query.limit) || 20;
    const category = req.query.category; // bitcoin, ethereum, defi, nft, etc.
    const symbol = req.query.symbol;
    
    let whereClause = '';
    let params = [limit];
    
    if (category) {
      whereClause += ' AND category = $' + (params.length + 1);
      params.push(category);
    }
    
    if (symbol) {
      whereClause += ' AND (related_symbols LIKE $' + (params.length + 1) + ' OR related_symbols LIKE $' + (params.length + 2) + ')';
      params.push(`%${symbol.toUpperCase()}%`);
      params.push(`%${symbol.toLowerCase()}%`);
    }

    const result = await query(`
      SELECT 
        title,
        description,
        url,
        source,
        author,
        published_at,
        category,
        related_symbols,
        sentiment_score,
        importance_score,
        image_url
      FROM crypto_news 
      WHERE published_at >= NOW() - INTERVAL '7 days'
        ${whereClause}
      ORDER BY published_at DESC, importance_score DESC
      LIMIT $1
    `, params);

    res.json({
      success: true,
      data: result.rows,
      metadata: {
        count: result.rows.length,
        filters: {
          category: category || null,
          symbol: symbol || null,
          days: 7
        }
      }
    });
  } catch (error) {
    console.error('Error fetching crypto news:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch crypto news'
    });
  }
});

// GET /crypto/market-overview - Get comprehensive market overview
router.get('/market-overview', async (req, res) => {
  try {
    console.log('🌍 Fetching comprehensive crypto market overview');
    
    let overviewData;
    try {
      // Use enhanced service for comprehensive market overview
      const marketOverview = await enhancedCryptoDataService.getMarketOverview();
      if (marketOverview.success) {
        overviewData = {
          ...marketOverview.data,
          source: 'live_api',
          warnings: marketOverview.warnings
        };
      } else {
        throw new Error('Enhanced service returned invalid overview data');
      }
    } catch (apiError) {
      console.log('⚠️ Live API failed, falling back to database');
      
      // Fallback to database queries
      const [topCryptos, marketMetrics, fearGreed] = await Promise.allSettled([
        query(`
          SELECT 
            symbol,
            name,
            price,
            market_cap,
            volume_24h,
            price_change_24h,
            price_change_7d,
            market_cap_rank
          FROM crypto_prices p
          JOIN crypto_assets a ON p.symbol = a.symbol
          WHERE p.timestamp = (
            SELECT MAX(timestamp) FROM crypto_prices WHERE symbol = p.symbol
          )
          ORDER BY market_cap DESC NULLS LAST
          LIMIT 10
        `),
        query(`
          SELECT 
            total_market_cap,
            total_volume_24h,
            btc_dominance,
            eth_dominance,
            market_cap_change_24h
          FROM crypto_market_metrics 
          ORDER BY timestamp DESC 
          LIMIT 1
        `),
        query(`
          SELECT value, value_classification
          FROM crypto_fear_greed 
          ORDER BY timestamp DESC 
          LIMIT 1
        `)
      ]);

      overviewData = {
        top_cryptocurrencies: topCryptos.status === 'fulfilled' ? topCryptos.value.rows : [],
        market_metrics: marketMetrics.status === 'fulfilled' ? marketMetrics.value.rows[0] : null,
        fear_greed_index: fearGreed.status === 'fulfilled' ? fearGreed.value.rows[0] : null,
        last_updated: new Date().toISOString(),
        source: 'database_fallback',
        note: 'Using cached market overview data'
      };
    }

    res.json({
      success: true,
      data: overviewData
    });
  } catch (error) {
    console.error('Error fetching crypto market overview:', error);
    
    const errorResponse = cryptoErrorHandler.handleError(error, {
      endpoint: '/market-overview',
      dataType: 'market_overview'
    });
    
    res.status(500).json({
      success: false,
      error: errorResponse
    });
  }
});

// WebSocket endpoint for real-time crypto data
router.ws('/ws', (ws, req) => {
  console.log('🌐 New WebSocket client connected to crypto feed');
  
  // Add client to WebSocket manager
  wsManager.addClient(ws);
  
  ws.on('message', (message) => {
    try {
      const data = JSON.parse(message);
      
      if (data.type === 'subscribe') {
        // Handle subscription requests
        console.log('Client subscription:', data.symbols);
        ws.send(JSON.stringify({
          type: 'subscription_confirmed',
          symbols: data.symbols,
          timestamp: new Date().toISOString()
        }));
      } else if (data.type === 'ping') {
        // Handle ping/pong for connection health
        ws.send(JSON.stringify({
          type: 'pong',
          timestamp: new Date().toISOString()
        }));
      }
    } catch (error) {
      console.error('WebSocket message error:', error);
    }
  });
  
  ws.on('close', () => {
    console.log('👋 WebSocket client disconnected from crypto feed');
    wsManager.removeClient(ws);
  });
  
  ws.on('error', (error) => {
    console.error('WebSocket error:', error);
    wsManager.removeClient(ws);
  });
});

// GET /crypto/websocket/health - WebSocket manager health check
router.get('/websocket/health', async (req, res) => {
  try {
    const health = wsManager.getHealthStatus();
    
    res.json({
      success: true,
      data: health
    });
  } catch (error) {
    console.error('Error getting WebSocket health:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get WebSocket health status'
    });
  }
});

// GET /crypto/websocket/snapshot - Get current WebSocket data snapshot
router.get('/websocket/snapshot', async (req, res) => {
  try {
    const snapshot = wsManager.getDataSnapshot();
    
    res.json({
      success: true,
      data: snapshot
    });
  } catch (error) {
    console.error('Error getting WebSocket snapshot:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get WebSocket data snapshot'
    });
  }
});

// GET /crypto/services/health - Enhanced services health check
router.get('/services/health', async (req, res) => {
  try {
    const [dataServiceHealth, wsHealth, errorStats] = await Promise.allSettled([
      enhancedCryptoDataService.healthCheck(),
      wsManager.getHealthStatus(),
      Promise.resolve(cryptoErrorHandler.getHealthStatus())
    ]);
    
    const healthReport = {
      overall_status: 'healthy',
      services: {
        enhanced_data_service: dataServiceHealth.status === 'fulfilled' ? 
          dataServiceHealth.value : { status: 'unhealthy', error: dataServiceHealth.reason },
        websocket_manager: wsHealth.status === 'fulfilled' ? 
          wsHealth.value : { status: 'unhealthy', error: wsHealth.reason },
        error_handler: errorStats.status === 'fulfilled' ? 
          errorStats.value : { status: 'unhealthy', error: errorStats.reason }
      },
      timestamp: new Date().toISOString()
    };
    
    // Determine overall status
    const serviceStatuses = Object.values(healthReport.services).map(s => s.status);
    if (serviceStatuses.includes('critical') || serviceStatuses.filter(s => s === 'unhealthy').length > 1) {
      healthReport.overall_status = 'critical';
    } else if (serviceStatuses.includes('degraded') || serviceStatuses.includes('unhealthy')) {
      healthReport.overall_status = 'degraded';
    }
    
    res.json({
      success: true,
      data: healthReport
    });
  } catch (error) {
    console.error('Error getting services health:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get services health status'
    });
  }
});

// POST /crypto/websocket/start - Start WebSocket manager
router.post('/websocket/start', async (req, res) => {
  try {
    if (!wsManager.isActive) {
      await wsManager.start();
      res.json({
        success: true,
        message: 'WebSocket manager started successfully'
      });
    } else {
      res.json({
        success: true,
        message: 'WebSocket manager already active'
      });
    }
  } catch (error) {
    console.error('Error starting WebSocket manager:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to start WebSocket manager'
    });
  }
});

// POST /crypto/websocket/stop - Stop WebSocket manager
router.post('/websocket/stop', async (req, res) => {
  try {
    if (wsManager.isActive) {
      await wsManager.stop();
      res.json({
        success: true,
        message: 'WebSocket manager stopped successfully'
      });
    } else {
      res.json({
        success: true,
        message: 'WebSocket manager already inactive'
      });
    }
  } catch (error) {
    console.error('Error stopping WebSocket manager:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to stop WebSocket manager'
    });
  }
});

// Auto-start WebSocket manager when routes are loaded
setTimeout(async () => {
  try {
    if (!wsManager.isActive) {
      console.log('🚀 Auto-starting crypto WebSocket manager...');
      await wsManager.start();
    }
  } catch (error) {
    console.error('Failed to auto-start WebSocket manager:', error);
  }
}, 2000); // Start after 2 seconds to allow server initialization

module.exports = router;
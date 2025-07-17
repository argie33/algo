const express = require('express');
const router = express.Router();
const { query } = require('../utils/database');

// Root crypto endpoint for health checks
router.get('/', (req, res) => {
  res.json({
    success: true,
    data: {
      system: 'Cryptocurrency API',
      version: '1.0.0',
      status: 'operational',
      available_endpoints: [
        'GET /crypto/market-metrics - Overall crypto market metrics',
        'GET /crypto/fear-greed - Fear and Greed Index',
        'GET /crypto/movers - Top gainers and losers',
        'GET /crypto/trending - Trending cryptocurrencies',
        'GET /crypto/assets - List of crypto assets',
        'GET /crypto/defi/tvl - DeFi Total Value Locked',
        'GET /crypto/exchanges - Exchange information'
      ],
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
      return res.status(404).json({
        success: false,
        error: 'No Fear and Greed data available'
      });
    }

    res.json({
      success: true,
      data: result.rows[0]
    });
  } catch (error) {
    console.error('Error fetching Fear and Greed index:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch Fear and Greed index'
    });
  }
});

// GET /crypto/movers - Get top gainers and losers
router.get('/movers', async (req, res) => {
  try {
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

    res.json({
      success: true,
      data: {
        gainers: gainersResult.rows,
        losers: losersResult.rows
      }
    });
  } catch (error) {
    console.error('Error fetching crypto movers:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch crypto movers'
    });
  }
});

// GET /crypto/trending - Get trending cryptocurrencies
router.get('/trending', async (req, res) => {
  try {
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

    res.json({
      success: true,
      data: result.rows
    });
  } catch (error) {
    console.error('Error fetching trending cryptos:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch trending cryptocurrencies'
    });
  }
});

// GET /crypto/prices/:symbol - Get price data for specific crypto
router.get('/prices/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const limit = parseInt(req.query.limit) || 100;
    
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

    res.json({
      success: true,
      data: result.rows
    });
  } catch (error) {
    console.error('Error fetching crypto prices:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch crypto prices'
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

    res.json({
      success: true,
      data: result.rows,
      pagination: {
        page,
        limit,
        total: parseInt(countResult.rows[0].total),
        pages: Math.ceil(parseInt(countResult.rows[0].total) / limit)
      }
    });
  } catch (error) {
    console.error('Error fetching crypto assets:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch crypto assets'
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
    
    // Calculate the date range
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

    res.json({
      success: true,
      data: result.rows,
      metadata: {
        symbol: symbol.toUpperCase(),
        days,
        interval,
        start_date: startDate.toISOString(),
        end_date: endDate.toISOString(),
        data_points: result.rows.length
      }
    });
  } catch (error) {
    console.error('Error fetching crypto historical data:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch crypto historical data'
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
    // Get top cryptocurrencies by market cap
    const topCryptos = await query(`
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
    `);

    // Get market metrics
    const marketMetrics = await query(`
      SELECT 
        total_market_cap,
        total_volume_24h,
        btc_dominance,
        eth_dominance,
        market_cap_change_24h
      FROM crypto_market_metrics 
      ORDER BY timestamp DESC 
      LIMIT 1
    `);

    // Get fear & greed index
    const fearGreed = await query(`
      SELECT value, value_classification
      FROM crypto_fear_greed 
      ORDER BY timestamp DESC 
      LIMIT 1
    `);

    res.json({
      success: true,
      data: {
        top_cryptocurrencies: topCryptos.rows,
        market_metrics: marketMetrics.rows[0] || null,
        fear_greed_index: fearGreed.rows[0] || null,
        last_updated: new Date().toISOString()
      }
    });
  } catch (error) {
    console.error('Error fetching crypto market overview:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch crypto market overview'
    });
  }
});

module.exports = router;
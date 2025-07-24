/**
 * Crypto Real-Time Data Streaming API
 * Provides WebSocket-like functionality for real-time crypto data
 */

const express = require('express');
const router = express.Router();
const axios = require('axios');

// In-memory cache for real-time data
const realtimeCache = new Map();
const priceAlerts = new Map();

// Price change thresholds
const SIGNIFICANT_CHANGE_THRESHOLD = 0.05; // 5%

/**
 * Get real-time price updates for multiple cryptocurrencies
 */
router.get('/prices', async (req, res) => {
    try {
        const { symbols, vs_currency = 'usd' } = req.query;
        
        if (!symbols) {
            return res.status(400).json({
                error: 'Symbols parameter is required',
                example: '/api/crypto-realtime/prices?symbols=bitcoin,ethereum,cardano'
            });
        }
        
        const symbolList = symbols.split(',');
        const cacheKey = `prices_${symbols}_${vs_currency}`;
        
        // Check cache first (30 second cache for real-time data)
        const cached = realtimeCache.get(cacheKey);
        if (cached && Date.now() - cached.timestamp < 30000) {
            return res.json({
                success: true,
                data: cached.data,
                cached: true,
                timestamp: cached.timestamp
            });
        }
        
        // Fetch real-time prices from CoinGecko
        const response = await axios.get('https://api.coingecko.com/api/v3/simple/price', {
            params: {
                ids: symbolList.join(','),
                vs_currencies: vs_currency,
                include_24hr_change: true,
                include_24hr_vol: true,
                include_last_updated_at: true
            },
            timeout: 10000
        });
        
        const priceData = response.data;
        
        // Process and enhance data
        const enhancedData = {};
        for (const [symbol, data] of Object.entries(priceData)) {
            const price = data[vs_currency];
            const change24h = data[`${vs_currency}_24h_change`] || 0;
            const volume24h = data[`${vs_currency}_24h_vol`] || 0;
            const lastUpdated = data.last_updated_at;
            
            enhancedData[symbol] = {
                symbol: symbol,
                price: price,
                change_24h: change24h,
                change_24h_percentage: change24h,
                volume_24h: volume24h,
                last_updated: lastUpdated,
                trend: change24h > 0 ? 'up' : change24h < 0 ? 'down' : 'neutral',
                significant_change: Math.abs(change24h) > SIGNIFICANT_CHANGE_THRESHOLD,
                formatted_price: new Intl.NumberFormat('en-US', {
                    style: 'currency',
                    currency: vs_currency.toUpperCase(),
                    minimumFractionDigits: 2,
                    maximumFractionDigits: price < 1 ? 6 : 2
                }).format(price),
                formatted_change: `${change24h > 0 ? '+' : ''}${change24h.toFixed(2)}%`
            };
        }
        
        // Update cache
        realtimeCache.set(cacheKey, {
            data: enhancedData,
            timestamp: Date.now()
        });
        
        res.json({
            success: true,
            data: enhancedData,
            cached: false,
            timestamp: Date.now(),
            symbols_requested: symbolList,
            symbols_found: Object.keys(enhancedData)
        });
        
    } catch (error) {
        console.error('Real-time prices error:', error);
        res.status(500).json({
            error: 'Failed to fetch real-time prices',
            message: error.message,
            timestamp: Date.now()
        });
    }
});

/**
 * Get real-time market overview with top movers
 */
router.get('/market-pulse', async (req, res) => {
    try {
        const { limit = 20, vs_currency = 'usd' } = req.query;
        
        const cacheKey = `market_pulse_${limit}_${vs_currency}`;
        const cached = realtimeCache.get(cacheKey);
        
        if (cached && Date.now() - cached.timestamp < 60000) { // 1 minute cache
            return res.json({
                success: true,
                data: cached.data,
                cached: true
            });
        }
        
        // Parallel API calls for comprehensive market data
        const [marketData, globalData, trendingData] = await Promise.all([
            // Top cryptocurrencies by market cap
            axios.get('https://api.coingecko.com/api/v3/coins/markets', {
                params: {
                    vs_currency: vs_currency,
                    order: 'market_cap_desc',
                    per_page: limit,
                    page: 1,
                    sparkline: false,
                    price_change_percentage: '1h,24h,7d'
                },
                timeout: 10000
            }),
            
            // Global market data
            axios.get('https://api.coingecko.com/api/v3/global', {
                timeout: 10000
            }),
            
            // Trending coins
            axios.get('https://api.coingecko.com/api/v3/search/trending', {
                timeout: 10000
            })
        ]);
        
        const coins = marketData.data;
        const global = globalData.data.data;
        const trending = trendingData.data.coins;
        
        // Process market data
        const processedCoins = coins.map(coin => ({
            id: coin.id,
            symbol: coin.symbol.toUpperCase(),
            name: coin.name,
            image: coin.image,
            current_price: coin.current_price,
            market_cap: coin.market_cap,
            market_cap_rank: coin.market_cap_rank,
            price_change_1h: coin.price_change_percentage_1h_in_currency,
            price_change_24h: coin.price_change_percentage_24h,
            price_change_7d: coin.price_change_percentage_7d_in_currency,
            volume_24h: coin.total_volume,
            circulating_supply: coin.circulating_supply,
            max_supply: coin.max_supply,
            ath: coin.ath,
            ath_change_percentage: coin.ath_change_percentage,
            formatted_price: new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: vs_currency.toUpperCase(),
                minimumFractionDigits: 2,
                maximumFractionDigits: coin.current_price < 1 ? 6 : 2
            }).format(coin.current_price),
            formatted_market_cap: new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: vs_currency.toUpperCase(),
                notation: 'compact',
                maximumFractionDigits: 2
            }).format(coin.market_cap)
        }));
        
        // Find top movers
        const topGainers = processedCoins
            .filter(coin => coin.price_change_24h > 0)
            .sort((a, b) => b.price_change_24h - a.price_change_24h)
            .slice(0, 5);
            
        const topLosers = processedCoins
            .filter(coin => coin.price_change_24h < 0)
            .sort((a, b) => a.price_change_24h - b.price_change_24h)
            .slice(0, 5);
        
        // Process global data
        const marketOverview = {
            total_market_cap: global.total_market_cap[vs_currency],
            total_volume: global.total_volume[vs_currency],
            market_cap_change_24h: global.market_cap_change_percentage_24h_usd,
            active_cryptocurrencies: global.active_cryptocurrencies,
            markets: global.markets,
            market_cap_percentage: global.market_cap_percentage,
            bitcoin_dominance: global.market_cap_percentage.btc,
            ethereum_dominance: global.market_cap_percentage.eth
        };
        
        // Process trending data
        const trendingCoins = trending.slice(0, 10).map(item => ({
            id: item.item.id,
            symbol: item.item.symbol,
            name: item.item.name,
            thumb: item.item.thumb,
            market_cap_rank: item.item.market_cap_rank,
            score: item.item.score
        }));
        
        const responseData = {
            market_overview: marketOverview,
            top_coins: processedCoins,
            top_gainers: topGainers,
            top_losers: topLosers,
            trending_coins: trendingCoins,
            last_updated: new Date().toISOString()
        };
        
        // Update cache
        realtimeCache.set(cacheKey, {
            data: responseData,
            timestamp: Date.now()
        });
        
        res.json({
            success: true,
            data: responseData,
            cached: false
        });
        
    } catch (error) {
        console.error('Market pulse error:', error);
        res.status(500).json({
            error: 'Failed to fetch market pulse data',
            message: error.message
        });
    }
});

/**
 * Price alert management
 */
router.post('/alerts', async (req, res) => {
    try {
        const { user_id, symbol, target_price, condition, notification_type = 'price' } = req.body;
        
        if (!user_id || !symbol || !target_price || !condition) {
            return res.status(400).json({
                error: 'Missing required fields',
                required: ['user_id', 'symbol', 'target_price', 'condition']
            });
        }
        
        if (!['above', 'below'].includes(condition)) {
            return res.status(400).json({
                error: 'Invalid condition',
                valid_conditions: ['above', 'below']
            });
        }
        
        const alertId = `${user_id}_${symbol}_${Date.now()}`;
        const alert = {
            id: alertId,
            user_id,
            symbol,
            target_price: parseFloat(target_price),
            condition,
            notification_type,
            created_at: new Date().toISOString(),
            triggered: false,
            active: true
        };
        
        // Store alert in memory (in production, this would be in database)
        if (!priceAlerts.has(user_id)) {
            priceAlerts.set(user_id, new Map());
        }
        priceAlerts.get(user_id).set(alertId, alert);
        
        res.json({
            success: true,
            message: 'Price alert created successfully',
            alert: alert
        });
        
    } catch (error) {
        console.error('Create alert error:', error);
        res.status(500).json({
            error: 'Failed to create price alert',
            message: error.message
        });
    }
});

/**
 * Get user's price alerts
 */
router.get('/alerts/:user_id', async (req, res) => {
    try {
        const { user_id } = req.params;
        
        const userAlerts = priceAlerts.get(user_id);
        if (!userAlerts) {
            return res.json({
                success: true,
                data: [],
                message: 'No alerts found for user'
            });
        }
        
        const alerts = Array.from(userAlerts.values())
            .filter(alert => alert.active)
            .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
        
        res.json({
            success: true,
            data: alerts,
            count: alerts.length
        });
        
    } catch (error) {
        console.error('Get alerts error:', error);
        res.status(500).json({
            error: 'Failed to fetch price alerts',
            message: error.message
        });
    }
});

/**
 * Delete price alert
 */
router.delete('/alerts/:alert_id', async (req, res) => {
    try {
        const { alert_id } = req.params;
        const { user_id } = req.query;
        
        if (!user_id) {
            return res.status(400).json({
                error: 'user_id query parameter is required'
            });
        }
        
        const userAlerts = priceAlerts.get(user_id);
        if (!userAlerts || !userAlerts.has(alert_id)) {
            return res.status(404).json({
                error: 'Alert not found'
            });
        }
        
        userAlerts.delete(alert_id);
        
        res.json({
            success: true,
            message: 'Price alert deleted successfully'
        });
        
    } catch (error) {
        console.error('Delete alert error:', error);
        res.status(500).json({
            error: 'Failed to delete price alert',
            message: error.message
        });
    }
});

/**
 * Historical price data for charts
 */
router.get('/history/:symbol', async (req, res) => {
    try {
        const { symbol } = req.params;
        const { days = 30, vs_currency = 'usd', interval = 'daily' } = req.query;
        
        const cacheKey = `history_${symbol}_${days}_${vs_currency}_${interval}`;
        const cached = realtimeCache.get(cacheKey);
        
        // Cache historical data for 5 minutes
        if (cached && Date.now() - cached.timestamp < 300000) {
            return res.json({
                success: true,
                data: cached.data,
                cached: true
            });
        }
        
        const response = await axios.get(`https://api.coingecko.com/api/v3/coins/${symbol}/market_chart`, {
            params: {
                vs_currency,
                days,
                interval: days <= 1 ? 'hourly' : interval
            },
            timeout: 15000
        });
        
        const { prices, market_caps, total_volumes } = response.data;
        
        // Process data for chart consumption
        const chartData = prices.map((price, index) => ({
            timestamp: price[0],
            date: new Date(price[0]).toISOString(),
            price: price[1],
            market_cap: market_caps[index] ? market_caps[index][1] : null,
            volume: total_volumes[index] ? total_volumes[index][1] : null,
            formatted_date: new Date(price[0]).toLocaleDateString(),
            formatted_price: new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: vs_currency.toUpperCase(),
                minimumFractionDigits: 2,
                maximumFractionDigits: price[1] < 1 ? 6 : 2
            }).format(price[1])
        }));
        
        // Calculate basic statistics
        const pricesOnly = chartData.map(d => d.price);
        const minPrice = Math.min(...pricesOnly);
        const maxPrice = Math.max(...pricesOnly);
        const firstPrice = pricesOnly[0];
        const lastPrice = pricesOnly[pricesOnly.length - 1];
        const totalReturn = ((lastPrice - firstPrice) / firstPrice) * 100;
        
        const responseData = {
            symbol,
            vs_currency,
            days: parseInt(days),
            interval,
            data: chartData,
            statistics: {
                min_price: minPrice,
                max_price: maxPrice,
                first_price: firstPrice,
                last_price: lastPrice,
                total_return_percentage: totalReturn,
                data_points: chartData.length
            }
        };
        
        // Update cache
        realtimeCache.set(cacheKey, {
            data: responseData,
            timestamp: Date.now()
        });
        
        res.json({
            success: true,
            data: responseData,
            cached: false
        });
        
    } catch (error) {
        console.error('Historical data error:', error);
        res.status(500).json({
            error: 'Failed to fetch historical data',
            message: error.message
        });
    }
});

/**
 * Cache management endpoints
 */
router.get('/cache/stats', (req, res) => {
    const stats = {
        cache_size: realtimeCache.size,
        alerts_count: Array.from(priceAlerts.values()).reduce((total, userAlerts) => total + userAlerts.size, 0),
        memory_usage: process.memoryUsage(),
        uptime: process.uptime()
    };
    
    res.json({
        success: true,
        data: stats
    });
});

router.post('/cache/clear', (req, res) => {
    realtimeCache.clear();
    res.json({
        success: true,
        message: 'Cache cleared successfully'
    });
});

module.exports = router;
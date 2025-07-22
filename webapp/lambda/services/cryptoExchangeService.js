/**
 * Crypto Exchange API Service
 * Real implementation to replace mock crypto data
 * Supports multiple exchanges: Binance, Coinbase Pro, Kraken
 */

const axios = require('axios');
const { getTimeout } = require('../utils/timeoutManager');
const crypto = require('crypto');

class CryptoExchangeService {
    constructor(exchangeName = 'binance', apiKey = null, apiSecret = null) {
        this.exchangeName = exchangeName.toLowerCase();
        this.apiKey = apiKey;
        this.apiSecret = apiSecret;
        
        // Exchange configurations
        this.exchanges = {
            binance: {
                baseUrl: 'https://api.binance.com',
                endpoints: {
                    ticker: '/api/v3/ticker/24hr',
                    klines: '/api/v3/klines',
                    trades: '/api/v3/trades',
                    orderbook: '/api/v3/depth'
                }
            },
            coinbase: {
                baseUrl: 'https://api.pro.coinbase.com',
                endpoints: {
                    ticker: '/products/{symbol}/ticker',
                    candles: '/products/{symbol}/candles',
                    trades: '/products/{symbol}/trades',
                    orderbook: '/products/{symbol}/book'
                }
            },
            kraken: {
                baseUrl: 'https://api.kraken.com/0/public',
                endpoints: {
                    ticker: '/Ticker',
                    ohlc: '/OHLC',
                    trades: '/Trades',
                    orderbook: '/Depth'
                }
            }
        };

        this.config = this.exchanges[this.exchangeName];
        if (!this.config) {
            throw new Error(`Unsupported exchange: ${exchangeName}`);
        }

        console.log(`🪙 Crypto Exchange Service initialized for ${exchangeName.toUpperCase()}`);
    }

    /**
     * Make API request with proper error handling
     */
    async makeRequest(endpoint, params = {}, requiresAuth = false) {
        const url = `${this.config.baseUrl}${endpoint}`;
        
        const config = {
            method: 'GET',
            url,
            params,
            timeout: getTimeout('market_data', 'realtime')
        };

        // Add authentication if required
        if (requiresAuth) {
            if (!this.apiKey || !this.apiSecret) {
                throw new Error(`API credentials required for ${this.exchangeName}`);
            }
            config.headers = this.getAuthHeaders(endpoint, params);
        }

        try {
            console.log(`📡 Making ${this.exchangeName} API request: ${endpoint}`);
            const response = await axios(config);
            return response.data;
        } catch (error) {
            console.error(`❌ ${this.exchangeName} API error:`, error.message);
            throw new Error(`${this.exchangeName} API error: ${error.message}`);
        }
    }

    /**
     * Get authentication headers (exchange-specific)
     */
    getAuthHeaders(endpoint, params) {
        switch (this.exchangeName) {
            case 'binance':
                return this.getBinanceAuthHeaders(endpoint, params);
            case 'coinbase':
                return this.getCoinbaseAuthHeaders(endpoint, params);
            case 'kraken':
                return this.getKrakenAuthHeaders(endpoint, params);
            default:
                return {};
        }
    }

    /**
     * Get current price for a symbol
     */
    async getPrice(symbol) {
        try {
            const normalizedSymbol = this.normalizeSymbol(symbol);
            console.log(`💰 Getting ${symbol} price from ${this.exchangeName}...`);

            let data;
            switch (this.exchangeName) {
                case 'binance':
                    data = await this.makeRequest(this.config.endpoints.ticker, { symbol: normalizedSymbol });
                    return {
                        symbol: symbol,
                        price: parseFloat(data.lastPrice),
                        change24h: parseFloat(data.priceChange),
                        changePercent24h: parseFloat(data.priceChangePercent),
                        volume24h: parseFloat(data.volume),
                        high24h: parseFloat(data.highPrice),
                        low24h: parseFloat(data.lowPrice),
                        timestamp: new Date(data.closeTime),
                        exchange: this.exchangeName
                    };

                case 'coinbase':
                    const endpoint = this.config.endpoints.ticker.replace('{symbol}', normalizedSymbol);
                    data = await this.makeRequest(endpoint);
                    return {
                        symbol: symbol,
                        price: parseFloat(data.price),
                        change24h: null, // Calculate if needed
                        changePercent24h: null,
                        volume24h: parseFloat(data.volume),
                        high24h: null,
                        low24h: null,
                        timestamp: new Date(data.time),
                        exchange: this.exchangeName
                    };

                case 'kraken':
                    data = await this.makeRequest(this.config.endpoints.ticker, { pair: normalizedSymbol });
                    const tickerData = data.result[Object.keys(data.result)[0]];
                    return {
                        symbol: symbol,
                        price: parseFloat(tickerData.c[0]), // Last trade price
                        change24h: null,
                        changePercent24h: null,
                        volume24h: parseFloat(tickerData.v[1]), // 24h volume
                        high24h: parseFloat(tickerData.h[1]), // 24h high
                        low24h: parseFloat(tickerData.l[1]), // 24h low
                        timestamp: new Date(),
                        exchange: this.exchangeName
                    };

                default:
                    throw new Error(`Price fetching not implemented for ${this.exchangeName}`);
            }
        } catch (error) {
            console.error(`❌ Failed to get ${symbol} price:`, error.message);
            throw error;
        }
    }

    /**
     * Get historical OHLCV data
     */
    async getHistoricalData(symbol, interval = '1d', limit = 100) {
        try {
            const normalizedSymbol = this.normalizeSymbol(symbol);
            console.log(`📊 Getting ${symbol} historical data (${interval}) from ${this.exchangeName}...`);

            let data;
            switch (this.exchangeName) {
                case 'binance':
                    const binanceInterval = this.convertInterval(interval, 'binance');
                    data = await this.makeRequest(this.config.endpoints.klines, {
                        symbol: normalizedSymbol,
                        interval: binanceInterval,
                        limit: limit
                    });
                    
                    return data.map(candle => ({
                        timestamp: new Date(candle[0]),
                        open: parseFloat(candle[1]),
                        high: parseFloat(candle[2]),
                        low: parseFloat(candle[3]),
                        close: parseFloat(candle[4]),
                        volume: parseFloat(candle[5])
                    }));

                case 'coinbase':
                    const coinbaseGranularity = this.convertInterval(interval, 'coinbase');
                    const endpoint = this.config.endpoints.candles.replace('{symbol}', normalizedSymbol);
                    data = await this.makeRequest(endpoint, {
                        granularity: coinbaseGranularity,
                        limit: limit
                    });
                    
                    return data.map(candle => ({
                        timestamp: new Date(candle[0] * 1000),
                        low: candle[1],
                        high: candle[2],
                        open: candle[3],
                        close: candle[4],
                        volume: candle[5]
                    }));

                case 'kraken':
                    const krakenInterval = this.convertInterval(interval, 'kraken');
                    data = await this.makeRequest(this.config.endpoints.ohlc, {
                        pair: normalizedSymbol,
                        interval: krakenInterval
                    });
                    
                    const ohlcData = data.result[Object.keys(data.result)[0]];
                    return ohlcData.slice(-limit).map(candle => ({
                        timestamp: new Date(candle[0] * 1000),
                        open: parseFloat(candle[1]),
                        high: parseFloat(candle[2]),
                        low: parseFloat(candle[3]),
                        close: parseFloat(candle[4]),
                        volume: parseFloat(candle[6])
                    }));

                default:
                    throw new Error(`Historical data not implemented for ${this.exchangeName}`);
            }
        } catch (error) {
            console.error(`❌ Failed to get ${symbol} historical data:`, error.message);
            throw error;
        }
    }

    /**
     * Get multiple cryptocurrency prices at once
     */
    async getMultiplePrices(symbols) {
        try {
            console.log(`💰 Getting prices for ${symbols.length} symbols from ${this.exchangeName}...`);

            if (this.exchangeName === 'binance') {
                // Binance supports getting all tickers at once
                const data = await this.makeRequest(this.config.endpoints.ticker);
                
                const priceMap = {};
                data.forEach(ticker => {
                    const originalSymbol = this.denormalizeSymbol(ticker.symbol);
                    if (symbols.includes(originalSymbol)) {
                        priceMap[originalSymbol] = {
                            symbol: originalSymbol,
                            price: parseFloat(ticker.lastPrice),
                            change24h: parseFloat(ticker.priceChange),
                            changePercent24h: parseFloat(ticker.priceChangePercent),
                            volume24h: parseFloat(ticker.volume),
                            timestamp: new Date(ticker.closeTime),
                            exchange: this.exchangeName
                        };
                    }
                });

                return symbols.map(symbol => priceMap[symbol] || { symbol, error: 'Not found' });
            } else {
                // For other exchanges, make individual requests
                const promises = symbols.map(symbol => 
                    this.getPrice(symbol).catch(error => ({ symbol, error: error.message }))
                );
                return await Promise.all(promises);
            }
        } catch (error) {
            console.error(`❌ Failed to get multiple prices:`, error.message);
            throw error;
        }
    }

    /**
     * Get top cryptocurrencies by market cap
     */
    async getTopCryptos(limit = 20) {
        try {
            console.log(`🔥 Getting top ${limit} cryptocurrencies from ${this.exchangeName}...`);

            if (this.exchangeName === 'binance') {
                const data = await this.makeRequest(this.config.endpoints.ticker);
                
                // Filter for major trading pairs (USDT pairs)
                const usdtPairs = data
                    .filter(ticker => ticker.symbol.endsWith('USDT') && 
                           !ticker.symbol.includes('UP') && 
                           !ticker.symbol.includes('DOWN'))
                    .sort((a, b) => parseFloat(b.quoteVolume) - parseFloat(a.quoteVolume))
                    .slice(0, limit);

                return usdtPairs.map(ticker => ({
                    symbol: ticker.symbol.replace('USDT', ''),
                    fullSymbol: ticker.symbol,
                    price: parseFloat(ticker.lastPrice),
                    change24h: parseFloat(ticker.priceChange),
                    changePercent24h: parseFloat(ticker.priceChangePercent),
                    volume24h: parseFloat(ticker.quoteVolume),
                    rank: null, // Would need CoinMarketCap API for actual rankings
                    exchange: this.exchangeName
                }));
            } else {
                throw new Error(`Top cryptos not implemented for ${this.exchangeName}`);
            }
        } catch (error) {
            console.error(`❌ Failed to get top cryptocurrencies:`, error.message);
            throw error;
        }
    }

    /**
     * Normalize symbol for exchange-specific format
     */
    normalizeSymbol(symbol) {
        switch (this.exchangeName) {
            case 'binance':
                return symbol.toUpperCase().replace('-', '');
            case 'coinbase':
                return symbol.toUpperCase().replace('/', '-');
            case 'kraken':
                return symbol.toUpperCase();
            default:
                return symbol.toUpperCase();
        }
    }

    /**
     * Convert symbol back to standard format
     */
    denormalizeSymbol(exchangeSymbol) {
        switch (this.exchangeName) {
            case 'binance':
                // Convert BTCUSDT back to BTC
                if (exchangeSymbol.endsWith('USDT')) {
                    return exchangeSymbol.replace('USDT', '');
                }
                return exchangeSymbol;
            default:
                return exchangeSymbol;
        }
    }

    /**
     * Convert interval to exchange-specific format
     */
    convertInterval(interval, exchange) {
        const intervalMap = {
            binance: { '1m': '1m', '5m': '5m', '1h': '1h', '1d': '1d', '1w': '1w' },
            coinbase: { '1m': 60, '5m': 300, '1h': 3600, '1d': 86400 },
            kraken: { '1m': 1, '5m': 5, '1h': 60, '1d': 1440, '1w': 10080 }
        };

        return intervalMap[exchange][interval] || intervalMap[exchange]['1d'];
    }

    /**
     * Get Binance authentication headers
     */
    getBinanceAuthHeaders(endpoint, params) {
        const timestamp = Date.now();
        const queryString = new URLSearchParams({ ...params, timestamp }).toString();
        const signature = crypto
            .createHmac('sha256', this.apiSecret)
            .update(queryString)
            .digest('hex');

        return {
            'X-MBX-APIKEY': this.apiKey
        };
    }

    /**
     * Get Coinbase authentication headers
     */
    getCoinbaseAuthHeaders(endpoint, params) {
        const timestamp = Date.now() / 1000;
        const method = 'GET';
        const requestPath = endpoint;
        const body = '';
        
        const message = timestamp + method + requestPath + body;
        const signature = crypto
            .createHmac('sha256', Buffer.from(this.apiSecret, 'base64'))
            .update(message)
            .digest('base64');

        return {
            'CB-ACCESS-KEY': this.apiKey,
            'CB-ACCESS-SIGN': signature,
            'CB-ACCESS-TIMESTAMP': timestamp,
            'CB-ACCESS-PASSPHRASE': process.env.COINBASE_PASSPHRASE || ''
        };
    }

    /**
     * Get Kraken authentication headers
     */
    getKrakenAuthHeaders(endpoint, params) {
        const nonce = Date.now() * 1000;
        const queryString = new URLSearchParams({ ...params, nonce }).toString();
        
        const message = endpoint + crypto.createHash('sha256').update(nonce + queryString).digest();
        const signature = crypto
            .createHmac('sha512', Buffer.from(this.apiSecret, 'base64'))
            .update(message)
            .digest('base64');

        return {
            'API-Key': this.apiKey,
            'API-Sign': signature
        };
    }

    /**
     * Validate API credentials
     */
    async validateCredentials() {
        if (!this.apiKey || !this.apiSecret) {
            return { valid: false, message: 'API credentials not provided' };
        }

        try {
            // Try a simple authenticated request
            await this.makeRequest('/api/v3/account', {}, true);
            return { valid: true, message: 'Credentials validated successfully' };
        } catch (error) {
            return { valid: false, message: `Credential validation failed: ${error.message}` };
        }
    }
}

module.exports = CryptoExchangeService;
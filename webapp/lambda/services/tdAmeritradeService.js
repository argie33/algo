/**
 * TD Ameritrade API Integration Service
 * Provides real integration with TD Ameritrade's API for portfolio management
 * Built to replace placeholder implementation
 */

const axios = require('axios');
const { getTimeout } = require('../utils/timeoutManager');
const logger = require('../utils/logger');

class TdAmeritradeService {
    constructor(apiKey, refreshToken, accessToken = null, accountId = null) {
        this.apiKey = apiKey;
        this.refreshToken = refreshToken;
        this.accessToken = accessToken;
        this.accountId = accountId;
        this.baseUrl = 'https://api.tdameritrade.com/v1';
        
        // Rate limiting
        this.lastRequestTime = 0;
        this.minRequestInterval = 500; // 500ms between requests to avoid rate limits
        
        console.log('🏦 TD Ameritrade service initialized');
    }

    /**
     * Get new access token using refresh token
     */
    async refreshAccessToken() {
        try {
            console.log('🔄 Refreshing TD Ameritrade access token...');
            
            const response = await axios.post('https://api.tdameritrade.com/v1/oauth2/token', {
                grant_type: 'refresh_token',
                refresh_token: this.refreshToken,
                client_id: this.apiKey
            }, {
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded'
                },
                timeout: getTimeout('auth', 'refresh')
            });

            this.accessToken = response.data.access_token;
            console.log('✅ TD Ameritrade access token refreshed successfully');
            
            return this.accessToken;
        } catch (error) {
            console.error('❌ Failed to refresh TD Ameritrade access token:', error.message);
            throw new Error(`Failed to refresh TD Ameritrade access token: ${error.message}`);
        }
    }

    /**
     * Make authenticated API request with rate limiting
     */
    async makeApiRequest(endpoint, method = 'GET', data = null) {
        // Implement rate limiting
        const now = Date.now();
        const timeSinceLastRequest = now - this.lastRequestTime;
        if (timeSinceLastRequest < this.minRequestInterval) {
            const waitTime = this.minRequestInterval - timeSinceLastRequest;
            console.log(`⏱️ Rate limiting: waiting ${waitTime}ms`);
            await new Promise(resolve => setTimeout(resolve, waitTime));
        }
        this.lastRequestTime = Date.now();

        // Ensure we have access token
        if (!this.accessToken) {
            await this.refreshAccessToken();
        }

        const config = {
            method,
            url: `${this.baseUrl}${endpoint}`,
            headers: {
                'Authorization': `Bearer ${this.accessToken}`,
                'Content-Type': 'application/json'
            },
            timeout: getTimeout('trading', method === 'POST' ? 'orders' : 'positions')
        };

        if (data) {
            config.data = data;
        }

        try {
            const response = await axios(config);
            return response.data;
        } catch (error) {
            if (error.response?.status === 401) {
                console.log('🔄 Access token expired, refreshing...');
                await this.refreshAccessToken();
                
                // Retry with new token
                config.headers.Authorization = `Bearer ${this.accessToken}`;
                const retryResponse = await axios(config);
                return retryResponse.data;
            }
            throw error;
        }
    }

    /**
     * Get user accounts
     */
    async getAccounts() {
        try {
            console.log('📊 Getting TD Ameritrade accounts...');
            
            const accounts = await this.makeApiRequest('/accounts');
            
            if (!this.accountId && accounts.length > 0) {
                this.accountId = accounts[0].securitiesAccount.accountId;
                console.log(`🔧 Auto-selected account ID: ${this.accountId}`);
            }

            return accounts.map(account => ({
                accountId: account.securitiesAccount.accountId,
                accountType: account.securitiesAccount.type,
                totalEquity: parseFloat(account.securitiesAccount.currentBalances?.equity || 0),
                buyingPower: parseFloat(account.securitiesAccount.currentBalances?.buyingPower || 0),
                cash: parseFloat(account.securitiesAccount.currentBalances?.cashBalance || 0),
                dayTradeCount: account.securitiesAccount.roundTrips || 0,
                isActive: true
            }));
        } catch (error) {
            console.error('❌ Failed to get TD Ameritrade accounts:', error.message);
            throw new Error(`Failed to get accounts: ${error.message}`);
        }
    }

    /**
     * Get portfolio positions
     */
    async getPositions() {
        try {
            if (!this.accountId) {
                await this.getAccounts();
            }

            console.log(`📈 Getting positions for TD Ameritrade account ${this.accountId}...`);
            
            const account = await this.makeApiRequest(`/accounts/${this.accountId}?fields=positions`);
            const positions = account.securitiesAccount?.positions || [];

            return positions
                .filter(position => position.longQuantity > 0 || position.shortQuantity > 0)
                .map(position => {
                    const instrument = position.instrument;
                    const quantity = position.longQuantity - position.shortQuantity;
                    const marketValue = position.marketValue;
                    const averagePrice = position.averagePrice;
                    
                    return {
                        symbol: instrument.symbol,
                        quantity: quantity,
                        averagePrice: averagePrice,
                        currentPrice: marketValue / quantity,
                        marketValue: marketValue,
                        unrealizedPL: marketValue - (averagePrice * quantity),
                        sector: this.getSectorFromInstrument(instrument),
                        assetType: instrument.assetType,
                        cusip: instrument.cusip
                    };
                });
        } catch (error) {
            console.error('❌ Failed to get TD Ameritrade positions:', error.message);
            throw new Error(`Failed to get positions: ${error.message}`);
        }
    }

    /**
     * Get account information
     */
    async getAccountInfo() {
        try {
            if (!this.accountId) {
                await this.getAccounts();
            }

            console.log(`ℹ️ Getting account info for TD Ameritrade account ${this.accountId}...`);
            
            const account = await this.makeApiRequest(`/accounts/${this.accountId}`);
            const balances = account.securitiesAccount.currentBalances;

            return {
                accountId: this.accountId,
                accountType: account.securitiesAccount.type,
                totalEquity: parseFloat(balances.equity || 0),
                buyingPower: parseFloat(balances.buyingPower || 0),
                cash: parseFloat(balances.cashBalance || 0),
                dayTradeCount: account.securitiesAccount.roundTrips || 0,
                accountValue: parseFloat(balances.liquidationValue || 0),
                longMarketValue: parseFloat(balances.longMarketValue || 0),
                shortMarketValue: parseFloat(balances.shortMarketValue || 0)
            };
        } catch (error) {
            console.error('❌ Failed to get TD Ameritrade account info:', error.message);
            throw new Error(`Failed to get account info: ${error.message}`);
        }
    }

    /**
     * Get trade history
     */
    async getTradeHistory(startDate = null, endDate = null) {
        try {
            if (!this.accountId) {
                await this.getAccounts();
            }

            const now = new Date();
            const defaultStartDate = new Date(now.getTime() - (30 * 24 * 60 * 60 * 1000)); // 30 days ago
            
            const fromDate = startDate || defaultStartDate.toISOString().split('T')[0];
            const toDate = endDate || now.toISOString().split('T')[0];

            console.log(`📋 Getting trade history for TD Ameritrade account ${this.accountId} from ${fromDate} to ${toDate}...`);
            
            const transactions = await this.makeApiRequest(
                `/accounts/${this.accountId}/transactions?type=TRADE&startDate=${fromDate}&endDate=${toDate}`
            );

            return transactions.map(transaction => ({
                transactionId: transaction.transactionId,
                symbol: transaction.transactionItem?.instrument?.symbol || 'N/A',
                side: transaction.type === 'BUY_TRADE' ? 'buy' : 'sell',
                quantity: Math.abs(transaction.transactionItem?.amount || 0),
                price: parseFloat(transaction.transactionItem?.price || 0),
                date: new Date(transaction.transactionDate),
                fees: parseFloat(transaction.fees?.rFee || 0) + parseFloat(transaction.fees?.additionalFee || 0),
                netAmount: parseFloat(transaction.netAmount || 0),
                description: transaction.description
            }));
        } catch (error) {
            console.error('❌ Failed to get TD Ameritrade trade history:', error.message);
            throw new Error(`Failed to get trade history: ${error.message}`);
        }
    }

    /**
     * Place a trade order
     */
    async placeOrder(orderConfig) {
        try {
            if (!this.accountId) {
                await this.getAccounts();
            }

            const {
                symbol,
                quantity,
                side, // 'BUY' or 'SELL'
                orderType = 'MARKET', // 'MARKET', 'LIMIT', 'STOP'
                price = null,
                timeInForce = 'DAY' // 'DAY', 'GTC', 'FOK', 'IOC'
            } = orderConfig;

            console.log(`📝 Placing ${side} order for ${quantity} shares of ${symbol}...`);

            const orderSpec = {
                orderType,
                session: 'NORMAL',
                duration: timeInForce,
                orderStrategyType: 'SINGLE',
                orderLegCollection: [{
                    instruction: side.toUpperCase(),
                    quantity,
                    instrument: {
                        symbol: symbol.toUpperCase(),
                        assetType: 'EQUITY'
                    }
                }]
            };

            if (orderType === 'LIMIT' && price) {
                orderSpec.price = price;
            }

            const response = await this.makeApiRequest(
                `/accounts/${this.accountId}/orders`,
                'POST',
                orderSpec
            );

            console.log('✅ Order placed successfully');
            return {
                success: true,
                orderId: response.orderId || 'N/A',
                message: 'Order placed successfully'
            };
        } catch (error) {
            console.error('❌ Failed to place TD Ameritrade order:', error.message);
            throw new Error(`Failed to place order: ${error.message}`);
        }
    }

    /**
     * Get quote for symbol
     */
    async getQuote(symbol) {
        try {
            console.log(`💰 Getting quote for ${symbol}...`);
            
            const quotes = await this.makeApiRequest(`/marketdata/${symbol}/quotes`);
            const quote = quotes[symbol];

            if (!quote) {
                throw new Error(`No quote data for ${symbol}`);
            }

            return {
                symbol: quote.symbol,
                price: quote.lastPrice,
                bid: quote.bidPrice,
                ask: quote.askPrice,
                volume: quote.totalVolume,
                change: quote.netChange,
                changePercent: quote.netPercentChangeInDouble,
                high: quote.highPrice,
                low: quote.lowPrice,
                open: quote.openPrice,
                close: quote.closePrice
            };
        } catch (error) {
            console.error(`❌ Failed to get quote for ${symbol}:`, error.message);
            throw new Error(`Failed to get quote: ${error.message}`);
        }
    }

    /**
     * Helper method to map instrument type to sector
     */
    getSectorFromInstrument(instrument) {
        // This is a simplified mapping - in production you'd use a more comprehensive database
        const sectorMapping = {
            'EQUITY': 'Equity',
            'OPTION': 'Options',
            'MUTUAL_FUND': 'Mutual Funds',
            'CASH_EQUIVALENT': 'Cash',
            'FIXED_INCOME': 'Fixed Income'
        };
        
        return sectorMapping[instrument.assetType] || 'Other';
    }

    /**
     * Validate API credentials
     */
    async validateCredentials() {
        try {
            console.log('🔐 Validating TD Ameritrade credentials...');
            await this.getAccounts();
            console.log('✅ TD Ameritrade credentials validated successfully');
            return { valid: true, message: 'Credentials validated successfully' };
        } catch (error) {
            console.error('❌ TD Ameritrade credential validation failed:', error.message);
            return { valid: false, message: `Credential validation failed: ${error.message}` };
        }
    }
}

module.exports = TdAmeritradeService;
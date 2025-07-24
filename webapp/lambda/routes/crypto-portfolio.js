/**
 * Crypto Portfolio Management API
 * Comprehensive portfolio tracking and management for cryptocurrencies
 */

const express = require('express');
const router = express.Router();
const axios = require('axios');

// In-memory portfolio storage (in production, this would be database)
const portfolios = new Map();
const portfolioTransactions = new Map();

/**
 * Get user's crypto portfolio
 */
router.get('/:user_id', async (req, res) => {
    try {
        const { user_id } = req.params;
        const { vs_currency = 'usd' } = req.query;
        
        const portfolio = portfolios.get(user_id) || {
            user_id,
            holdings: new Map(),
            created_at: new Date().toISOString(),
            last_updated: new Date().toISOString()
        };
        
        if (portfolio.holdings.size === 0) {
            return res.json({
                success: true,
                data: {
                    user_id,
                    total_value: 0,
                    total_cost: 0,
                    total_pnl: 0,
                    total_pnl_percentage: 0,
                    holdings: [],
                    allocation: {},
                    performance: {
                        day_change: 0,
                        week_change: 0,
                        month_change: 0
                    }
                }
            });
        }
        
        // Get current prices for all holdings
        const symbols = Array.from(portfolio.holdings.keys());
        const priceResponse = await axios.get('https://api.coingecko.com/api/v3/simple/price', {
            params: {
                ids: symbols.join(','),
                vs_currencies: vs_currency,
                include_24hr_change: true,
                include_7d_change: true,
                include_30d_change: true
            },
            timeout: 10000
        });
        
        const currentPrices = priceResponse.data;
        
        // Calculate portfolio metrics
        let totalValue = 0;
        let totalCost = 0;
        let totalDayChange = 0;
        
        const holdings = [];
        const allocation = {};
        
        for (const [symbol, holding] of portfolio.holdings.entries()) {
            const currentPrice = currentPrices[symbol]?.[vs_currency] || 0;
            const dayChange = currentPrices[symbol]?.[`${vs_currency}_24h_change`] || 0;
            const weekChange = currentPrices[symbol]?.[`${vs_currency}_7d_change`] || 0;
            const monthChange = currentPrices[symbol]?.[`${vs_currency}_30d_change`] || 0;
            
            const currentValue = holding.quantity * currentPrice;
            const totalCostForHolding = holding.average_cost * holding.quantity;
            const unrealizedPnL = currentValue - totalCostForHolding;
            const unrealizedPnLPercentage = totalCostForHolding > 0 ? (unrealizedPnL / totalCostForHolding) * 100 : 0;
            
            const holdingData = {
                symbol,
                name: holding.name,
                quantity: holding.quantity,
                average_cost: holding.average_cost,
                current_price: currentPrice,
                current_value: currentValue,
                total_cost: totalCostForHolding,
                unrealized_pnl: unrealizedPnL,
                unrealized_pnl_percentage: unrealizedPnLPercentage,
                day_change: dayChange,
                week_change: weekChange,
                month_change: monthChange,
                day_pnl: currentValue * (dayChange / 100),
                first_purchased: holding.first_purchased,
                last_transaction: holding.last_transaction,
                formatted_value: new Intl.NumberFormat('en-US', {
                    style: 'currency',
                    currency: vs_currency.toUpperCase()
                }).format(currentValue),
                formatted_pnl: new Intl.NumberFormat('en-US', {
                    style: 'currency',
                    currency: vs_currency.toUpperCase()
                }).format(unrealizedPnL)
            };
            
            holdings.push(holdingData);
            totalValue += currentValue;
            totalCost += totalCostForHolding;
            totalDayChange += currentValue * (dayChange / 100);
        }
        
        // Calculate allocation percentages
        holdings.forEach(holding => {
            allocation[holding.symbol] = {
                percentage: totalValue > 0 ? (holding.current_value / totalValue) * 100 : 0,
                value: holding.current_value
            };
        });
        
        const totalPnL = totalValue - totalCost;
        const totalPnLPercentage = totalCost > 0 ? (totalPnL / totalCost) * 100 : 0;
        const dayChangePercentage = totalValue > 0 ? (totalDayChange / totalValue) * 100 : 0;
        
        res.json({
            success: true,
            data: {
                user_id,
                total_value: totalValue,
                total_cost: totalCost,
                total_pnl: totalPnL,
                total_pnl_percentage: totalPnLPercentage,
                holdings: holdings.sort((a, b) => b.current_value - a.current_value),
                allocation,
                performance: {
                    day_change: totalDayChange,
                    day_change_percentage: dayChangePercentage,
                    total_return: totalPnLPercentage
                },
                summary: {
                    total_assets: holdings.length,
                    best_performer: holdings.reduce((best, current) => 
                        current.unrealized_pnl_percentage > best.unrealized_pnl_percentage ? current : best, 
                        holdings[0] || {}),
                    worst_performer: holdings.reduce((worst, current) => 
                        current.unrealized_pnl_percentage < worst.unrealized_pnl_percentage ? current : worst, 
                        holdings[0] || {}),
                    largest_holding: holdings[0] || {},
                    formatted_total_value: new Intl.NumberFormat('en-US', {
                        style: 'currency',
                        currency: vs_currency.toUpperCase()
                    }).format(totalValue)
                },
                last_updated: new Date().toISOString()
            }
        });
        
    } catch (error) {
        console.error('Get portfolio error:', error);
        res.status(500).json({
            error: 'Failed to fetch portfolio',
            message: error.message
        });
    }
});

/**
 * Add transaction to portfolio
 */
router.post('/:user_id/transactions', async (req, res) => {
    try {
        const { user_id } = req.params;
        const { 
            symbol, 
            name, 
            type, 
            quantity, 
            price, 
            fee = 0, 
            exchange = 'manual',
            notes = ''
        } = req.body;
        
        // Validate required fields
        if (!symbol || !type || !quantity || !price) {
            return res.status(400).json({
                error: 'Missing required fields',
                required: ['symbol', 'type', 'quantity', 'price'],
                received: { symbol, type, quantity, price }
            });
        }
        
        if (!['buy', 'sell'].includes(type)) {
            return res.status(400).json({
                error: 'Invalid transaction type',
                valid_types: ['buy', 'sell']
            });
        }
        
        const transactionId = `${user_id}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        const transaction = {
            id: transactionId,
            user_id,
            symbol: symbol.toLowerCase(),
            name: name || symbol.toUpperCase(),
            type,
            quantity: parseFloat(quantity),
            price: parseFloat(price),
            fee: parseFloat(fee),
            total: type === 'buy' ? 
                (parseFloat(quantity) * parseFloat(price)) + parseFloat(fee) :
                (parseFloat(quantity) * parseFloat(price)) - parseFloat(fee),
            exchange,
            notes,
            timestamp: new Date().toISOString(),
            date: new Date().toISOString().split('T')[0]
        };
        
        // Store transaction
        if (!portfolioTransactions.has(user_id)) {
            portfolioTransactions.set(user_id, []);
        }
        portfolioTransactions.get(user_id).push(transaction);
        
        // Update portfolio holdings
        let portfolio = portfolios.get(user_id);
        if (!portfolio) {
            portfolio = {
                user_id,
                holdings: new Map(),
                created_at: new Date().toISOString(),
                last_updated: new Date().toISOString()
            };
            portfolios.set(user_id, portfolio);
        }
        
        const currentHolding = portfolio.holdings.get(symbol.toLowerCase()) || {
            symbol: symbol.toLowerCase(),
            name: name || symbol.toUpperCase(),
            quantity: 0,
            total_cost: 0,
            average_cost: 0,
            first_purchased: transaction.timestamp,
            last_transaction: transaction.timestamp
        };
        
        if (type === 'buy') {
            const newTotalCost = currentHolding.total_cost + transaction.total;
            const newQuantity = currentHolding.quantity + transaction.quantity;
            
            currentHolding.quantity = newQuantity;
            currentHolding.total_cost = newTotalCost;
            currentHolding.average_cost = newQuantity > 0 ? newTotalCost / newQuantity : 0;
            currentHolding.last_transaction = transaction.timestamp;
            
        } else if (type === 'sell') {
            if (currentHolding.quantity < transaction.quantity) {
                return res.status(400).json({
                    error: 'Insufficient holdings to sell',
                    current_quantity: currentHolding.quantity,
                    sell_quantity: transaction.quantity
                });
            }
            
            const soldCostBasis = currentHolding.average_cost * transaction.quantity;
            currentHolding.quantity -= transaction.quantity;
            currentHolding.total_cost -= soldCostBasis;
            currentHolding.last_transaction = transaction.timestamp;
            
            // Calculate realized P&L for the sale
            transaction.realized_pnl = transaction.total - soldCostBasis - transaction.fee;
        }
        
        // Remove holding if quantity becomes 0
        if (currentHolding.quantity <= 0) {
            portfolio.holdings.delete(symbol.toLowerCase());
        } else {
            portfolio.holdings.set(symbol.toLowerCase(), currentHolding);
        }
        
        portfolio.last_updated = new Date().toISOString();
        
        res.json({
            success: true,
            message: 'Transaction added successfully',
            data: {
                transaction: transaction,
                updated_holding: currentHolding.quantity > 0 ? currentHolding : null,
                portfolio_summary: {
                    total_holdings: portfolio.holdings.size,
                    last_updated: portfolio.last_updated
                }
            }
        });
        
    } catch (error) {
        console.error('Add transaction error:', error);
        res.status(500).json({
            error: 'Failed to add transaction',
            message: error.message
        });
    }
});

/**
 * Get portfolio transactions history
 */
router.get('/:user_id/transactions', async (req, res) => {
    try {
        const { user_id } = req.params;
        const { limit = 50, offset = 0, type, symbol, start_date, end_date } = req.query;
        
        const userTransactions = portfolioTransactions.get(user_id) || [];
        
        // Apply filters
        let filteredTransactions = [...userTransactions];
        
        if (type) {
            filteredTransactions = filteredTransactions.filter(t => t.type === type);
        }
        
        if (symbol) {
            filteredTransactions = filteredTransactions.filter(t => 
                t.symbol.toLowerCase() === symbol.toLowerCase()
            );
        }
        
        if (start_date) {
            filteredTransactions = filteredTransactions.filter(t => 
                new Date(t.timestamp) >= new Date(start_date)
            );
        }
        
        if (end_date) {
            filteredTransactions = filteredTransactions.filter(t => 
                new Date(t.timestamp) <= new Date(end_date)
            );
        }
        
        // Sort by timestamp (newest first)
        filteredTransactions.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
        
        // Apply pagination
        const startIndex = parseInt(offset);
        const endIndex = startIndex + parseInt(limit);
        const paginatedTransactions = filteredTransactions.slice(startIndex, endIndex);
        
        // Add formatted data
        const enhancedTransactions = paginatedTransactions.map(transaction => ({
            ...transaction,
            formatted_total: new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: 'USD'
            }).format(transaction.total),
            formatted_price: new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: 'USD',
                minimumFractionDigits: 2,
                maximumFractionDigits: transaction.price < 1 ? 6 : 2
            }).format(transaction.price),
            formatted_date: new Date(transaction.timestamp).toLocaleDateString(),
            formatted_time: new Date(transaction.timestamp).toLocaleTimeString()
        }));
        
        // Calculate summary statistics
        const summary = {
            total_transactions: filteredTransactions.length,
            buy_transactions: filteredTransactions.filter(t => t.type === 'buy').length,
            sell_transactions: filteredTransactions.filter(t => t.type === 'sell').length,
            total_invested: filteredTransactions
                .filter(t => t.type === 'buy')
                .reduce((sum, t) => sum + t.total, 0),
            total_sold: filteredTransactions
                .filter(t => t.type === 'sell')
                .reduce((sum, t) => sum + t.total, 0),
            total_fees: filteredTransactions.reduce((sum, t) => sum + t.fee, 0),
            realized_pnl: filteredTransactions
                .filter(t => t.realized_pnl)
                .reduce((sum, t) => sum + t.realized_pnl, 0)
        };
        
        res.json({
            success: true,
            data: {
                transactions: enhancedTransactions,
                summary,
                pagination: {
                    total: filteredTransactions.length,
                    limit: parseInt(limit),
                    offset: parseInt(offset),
                    has_more: endIndex < filteredTransactions.length
                }
            }
        });
        
    } catch (error) {
        console.error('Get transactions error:', error);
        res.status(500).json({
            error: 'Failed to fetch transactions',
            message: error.message
        });
    }
});

/**
 * Delete transaction
 */
router.delete('/:user_id/transactions/:transaction_id', async (req, res) => {
    try {
        const { user_id, transaction_id } = req.params;
        
        const userTransactions = portfolioTransactions.get(user_id);
        if (!userTransactions) {
            return res.status(404).json({
                error: 'No transactions found for user'
            });
        }
        
        const transactionIndex = userTransactions.findIndex(t => t.id === transaction_id);
        if (transactionIndex === -1) {
            return res.status(404).json({
                error: 'Transaction not found'
            });
        }
        
        const deletedTransaction = userTransactions.splice(transactionIndex, 1)[0];
        
        // Recalculate portfolio after deletion
        // This is a simplified approach - in production, you'd want to rebuild from all remaining transactions
        const portfolio = portfolios.get(user_id);
        if (portfolio) {
            portfolio.last_updated = new Date().toISOString();
        }
        
        res.json({
            success: true,
            message: 'Transaction deleted successfully',
            deleted_transaction: deletedTransaction
        });
        
    } catch (error) {
        console.error('Delete transaction error:', error);
        res.status(500).json({
            error: 'Failed to delete transaction',
            message: error.message
        });
    }
});

/**
 * Portfolio performance analytics
 */
router.get('/:user_id/analytics', async (req, res) => {
    try {
        const { user_id } = req.params;
        const { period = '30d', vs_currency = 'usd' } = req.query;
        
        const portfolio = portfolios.get(user_id);
        const transactions = portfolioTransactions.get(user_id) || [];
        
        if (!portfolio || portfolio.holdings.size === 0) {
            return res.json({
                success: true,
                data: {
                    message: 'No portfolio data available for analytics',
                    portfolio_value: 0,
                    performance_metrics: {}
                }
            });
        }
        
        // Get current portfolio value
        const symbols = Array.from(portfolio.holdings.keys());
        const priceResponse = await axios.get('https://api.coingecko.com/api/v3/simple/price', {
            params: {
                ids: symbols.join(','),
                vs_currencies: vs_currency,
                include_24hr_change: true
            },
            timeout: 10000
        });
        
        const currentPrices = priceResponse.data;
        let currentPortfolioValue = 0;
        
        for (const [symbol, holding] of portfolio.holdings.entries()) {
            const currentPrice = currentPrices[symbol]?.[vs_currency] || 0;
            currentPortfolioValue += holding.quantity * currentPrice;
        }
        
        // Calculate performance metrics
        const totalInvested = transactions
            .filter(t => t.type === 'buy')
            .reduce((sum, t) => sum + t.total, 0);
            
        const totalSold = transactions
            .filter(t => t.type === 'sell')
            .reduce((sum, t) => sum + t.total, 0);
            
        const realizedPnL = transactions
            .filter(t => t.realized_pnl)
            .reduce((sum, t) => sum + t.realized_pnl, 0);
            
        const unrealizedPnL = currentPortfolioValue - (totalInvested - totalSold);
        const totalPnL = realizedPnL + unrealizedPnL;
        const totalReturn = totalInvested > 0 ? (totalPnL / totalInvested) * 100 : 0;
        
        // Asset allocation analysis
        const allocation = {};
        let allocationData = [];
        
        for (const [symbol, holding] of portfolio.holdings.entries()) {
            const currentPrice = currentPrices[symbol]?.[vs_currency] || 0;
            const value = holding.quantity * currentPrice;
            const percentage = currentPortfolioValue > 0 ? (value / currentPortfolioValue) * 100 : 0;
            
            allocation[symbol] = { value, percentage };
            allocationData.push({
                symbol,
                name: holding.name,
                value,
                percentage,
                quantity: holding.quantity
            });
        }
        
        allocationData.sort((a, b) => b.value - a.value);
        
        // Risk metrics (simplified)
        const diversificationScore = portfolio.holdings.size >= 5 ? 'High' : 
                                   portfolio.holdings.size >= 3 ? 'Medium' : 'Low';
        
        const concentrationRisk = allocationData.length > 0 ? allocationData[0].percentage : 0;
        
        res.json({
            success: true,
            data: {
                portfolio_value: currentPortfolioValue,
                total_invested: totalInvested,
                total_sold: totalSold,
                realized_pnl: realizedPnL,
                unrealized_pnl: unrealizedPnL,
                total_pnl: totalPnL,
                total_return_percentage: totalReturn,
                allocation: allocationData,
                risk_metrics: {
                    diversification_score: diversificationScore,
                    concentration_risk: concentrationRisk,
                    largest_position: allocationData[0]?.symbol || 'N/A',
                    total_assets: portfolio.holdings.size
                },
                performance_summary: {
                    best_performer: allocationData[0] || {},
                    portfolio_age_days: Math.ceil(
                        (new Date() - new Date(portfolio.created_at)) / (1000 * 60 * 60 * 24)
                    ),
                    last_transaction: transactions.length > 0 ? 
                        transactions.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))[0].timestamp : 
                        null
                },
                formatted_values: {
                    portfolio_value: new Intl.NumberFormat('en-US', {
                        style: 'currency',
                        currency: vs_currency.toUpperCase()
                    }).format(currentPortfolioValue),
                    total_pnl: new Intl.NumberFormat('en-US', {
                        style: 'currency',
                        currency: vs_currency.toUpperCase()
                    }).format(totalPnL)
                }
            }
        });
        
    } catch (error) {
        console.error('Portfolio analytics error:', error);
        res.status(500).json({
            error: 'Failed to fetch portfolio analytics',
            message: error.message
        });
    }
});

module.exports = router;
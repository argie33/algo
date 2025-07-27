/**
 * Crypto Portfolio Routes
 * 
 * Dedicated routes for crypto portfolio management that match frontend expectations
 * These routes provide the exact API structure the frontend components expect
 */

const express = require('express');
const router = express.Router();
const cryptoPortfolioService = require('../services/cryptoPortfolioService');
const enhancedCryptoDataService = require('../services/enhancedCryptoDataService');
const cryptoErrorHandler = require('../utils/cryptoErrorHandler');
const { StructuredLogger } = require('../utils/structuredLogger');

const logger = new StructuredLogger('crypto-portfolio-routes');

// GET /crypto-portfolio/:userId - Get user's crypto portfolio (frontend expects this exact structure)
router.get('/:userId', async (req, res) => {
  try {
    const { userId } = req.params;
    const vs_currency = req.query.vs_currency || 'usd';
    
    logger.info('Fetching user crypto portfolio', { user_id: userId, vs_currency });
    
    const portfolioData = await cryptoPortfolioService.getUserPortfolio(userId, {
      includeTransactions: false,
      includePerformance: true
    });

    if (portfolioData.success) {
      // Transform data to match frontend expectations
      const transformedData = {
        holdings: portfolioData.data.holdings.map(holding => ({
          id: `${userId}_${holding.symbol}`,
          symbol: holding.symbol,
          name: holding.asset_name || holding.symbol,
          amount: holding.quantity,
          avgPrice: holding.average_cost,
          currentPrice: holding.current_price,
          value: holding.market_value,
          pnl: holding.unrealized_pnl,
          pnlPercent: holding.unrealized_pnl_percent,
          allocation: holding.allocation_percentage,
          lastUpdated: holding.last_updated || new Date().toISOString()
        })),
        summary: portfolioData.data.summary,
        performance: portfolioData.data.performance_metrics,
        lastUpdated: portfolioData.data.last_updated
      };

      res.json({
        success: true,
        data: transformedData
      });
    } else {
      throw new Error('Portfolio service returned error');
    }

  } catch (error) {
    logger.error('Failed to fetch user portfolio', error, { user_id: req.params.userId });
    
    const errorResponse = cryptoErrorHandler.handleError(error, {
      endpoint: '/crypto-portfolio/:userId',
      dataType: 'portfolio',
      userId: req.params.userId
    });
    
    res.status(500).json({
      success: false,
      error: errorResponse
    });
  }
});

// GET /crypto-portfolio/:userId/transactions - Get user's transaction history
router.get('/:userId/transactions', async (req, res) => {
  try {
    const { userId } = req.params;
    const limit = parseInt(req.query.limit) || 20;
    
    logger.info('Fetching user transactions', { user_id: userId, limit });
    
    const transactions = await cryptoPortfolioService.getRecentTransactions(userId, limit);

    // Transform transactions to match frontend expectations
    const transformedTransactions = transactions.map(tx => ({
      id: tx.id,
      type: tx.transaction_type.toLowerCase(),
      symbol: tx.symbol,
      name: tx.asset_name || tx.symbol,
      amount: tx.quantity,
      price: tx.price,
      value: tx.total_amount,
      fees: tx.fees || 0,
      date: tx.transaction_date,
      exchange: tx.exchange || 'Manual',
      notes: tx.notes || ''
    }));

    res.json({
      success: true,
      data: {
        transactions: transformedTransactions
      }
    });

  } catch (error) {
    logger.error('Failed to fetch user transactions', error, { user_id: req.params.userId });
    
    const errorResponse = cryptoErrorHandler.handleError(error, {
      endpoint: '/crypto-portfolio/:userId/transactions',
      dataType: 'transactions',
      userId: req.params.userId
    });
    
    res.status(500).json({
      success: false,
      error: errorResponse
    });
  }
});

// GET /crypto-portfolio/:userId/analytics - Get portfolio analytics
router.get('/:userId/analytics', async (req, res) => {
  try {
    const { userId } = req.params;
    
    logger.info('Fetching portfolio analytics', { user_id: userId });
    
    const performanceMetrics = await cryptoPortfolioService.calculatePerformanceMetrics(userId);
    const allocation = await cryptoPortfolioService.getPortfolioAllocation(userId);

    if (!performanceMetrics) {
      return res.json({
        success: true,
        data: {
          performance: null,
          allocation: [],
          diversification: null,
          risk: null
        }
      });
    }

    // Calculate additional analytics
    const analytics = {
      performance: {
        totalReturn: performanceMetrics.total_return_percentage,
        totalValue: performanceMetrics.total_value,
        totalCost: performanceMetrics.total_cost,
        totalPnl: performanceMetrics.total_pnl,
        positionCount: performanceMetrics.position_count,
        bestPerformer: performanceMetrics.best_performer,
        worstPerformer: performanceMetrics.worst_performer
      },
      allocation: allocation.success ? allocation.data : [],
      diversification: {
        assetCount: performanceMetrics.position_count,
        concentrationRisk: performanceMetrics.position_count < 5 ? 'High' : 
                          performanceMetrics.position_count < 10 ? 'Medium' : 'Low',
        largestHolding: allocation.success && allocation.data.length > 0 ? 
                       allocation.data[0].allocation_percentage : 0
      },
      risk: {
        volatility: 'Medium', // Placeholder - would calculate from price history
        drawdown: null, // Placeholder - would calculate from portfolio history
        beta: null, // Placeholder - would calculate correlation with market
        sharpe: null // Placeholder - would calculate risk-adjusted returns
      }
    };

    res.json({
      success: true,
      data: analytics
    });

  } catch (error) {
    logger.error('Failed to fetch portfolio analytics', error, { user_id: req.params.userId });
    
    const errorResponse = cryptoErrorHandler.handleError(error, {
      endpoint: '/crypto-portfolio/:userId/analytics',
      dataType: 'analytics',
      userId: req.params.userId
    });
    
    res.status(500).json({
      success: false,
      error: errorResponse
    });
  }
});

// POST /crypto-portfolio/:userId/holdings - Add or update holding
router.post('/:userId/holdings', async (req, res) => {
  try {
    const { userId } = req.params;
    const { symbol, amount, avgPrice, notes } = req.body;
    
    if (!symbol || amount === undefined || avgPrice === undefined) {
      return res.status(400).json({
        success: false,
        error: 'Missing required fields: symbol, amount, avgPrice'
      });
    }
    
    logger.info('Adding/updating portfolio holding', { 
      user_id: userId, 
      symbol, 
      amount, 
      avg_price: avgPrice 
    });
    
    const result = await cryptoPortfolioService.updateHolding(
      userId, 
      symbol, 
      parseFloat(amount), 
      parseFloat(avgPrice),
      'manual'
    );

    if (result.success) {
      // Transform response to match frontend expectations
      const transformedHolding = {
        id: `${userId}_${symbol}`,
        symbol: symbol,
        name: symbol, // Will be enriched by frontend
        amount: parseFloat(amount),
        avgPrice: parseFloat(avgPrice),
        currentPrice: result.data.current_price,
        value: result.data.market_value,
        pnl: result.data.unrealized_pnl,
        pnlPercent: result.data.unrealized_pnl_percent,
        lastUpdated: result.data.last_updated || new Date().toISOString()
      };

      res.json({
        success: true,
        data: transformedHolding
      });
    } else {
      throw new Error('Failed to update holding');
    }

  } catch (error) {
    logger.error('Failed to add/update holding', error, { 
      user_id: req.params.userId,
      symbol: req.body.symbol
    });
    
    const errorResponse = cryptoErrorHandler.handleError(error, {
      endpoint: '/crypto-portfolio/:userId/holdings',
      dataType: 'holding_update'
    });
    
    res.status(500).json({
      success: false,
      error: errorResponse
    });
  }
});

// DELETE /crypto-portfolio/:userId/holdings/:symbol - Remove holding
router.delete('/:userId/holdings/:symbol', async (req, res) => {
  try {
    const { userId, symbol } = req.params;
    
    logger.info('Removing portfolio holding', { user_id: userId, symbol });
    
    const result = await cryptoPortfolioService.deleteHolding(userId, symbol);

    res.json({
      success: true,
      data: {
        deleted: result.deleted,
        symbol: symbol,
        message: result.deleted ? 'Holding removed successfully' : 'Holding not found'
      }
    });

  } catch (error) {
    logger.error('Failed to remove holding', error, { 
      user_id: req.params.userId,
      symbol: req.params.symbol
    });
    
    const errorResponse = cryptoErrorHandler.handleError(error, {
      endpoint: '/crypto-portfolio/:userId/holdings/:symbol',
      dataType: 'holding_delete'
    });
    
    res.status(500).json({
      success: false,
      error: errorResponse
    });
  }
});

// POST /crypto-portfolio/:userId/transactions - Record transaction
router.post('/:userId/transactions', async (req, res) => {
  try {
    const { userId } = req.params;
    const { type, symbol, amount, price, fee = 0, exchange = 'Manual', notes = '' } = req.body;
    
    if (!type || !symbol || amount === undefined || price === undefined) {
      return res.status(400).json({
        success: false,
        error: 'Missing required fields: type, symbol, amount, price'
      });
    }
    
    logger.info('Recording crypto transaction', { 
      user_id: userId, 
      type, 
      symbol, 
      amount, 
      price 
    });
    
    const result = await cryptoPortfolioService.recordTransaction(
      userId, 
      symbol, 
      type.toUpperCase(),
      parseFloat(amount), 
      parseFloat(price),
      parseFloat(fee),
      exchange,
      notes
    );

    if (result.success) {
      // Transform response to match frontend expectations
      const transformedTransaction = {
        id: result.data.id,
        type: type.toLowerCase(),
        symbol: symbol,
        name: symbol, // Will be enriched by frontend
        amount: parseFloat(amount),
        price: parseFloat(price),
        value: result.data.total_amount,
        fees: parseFloat(fee),
        date: result.data.transaction_date,
        exchange: exchange,
        notes: notes
      };

      res.json({
        success: true,
        data: transformedTransaction
      });
    } else {
      throw new Error('Failed to record transaction');
    }

  } catch (error) {
    logger.error('Failed to record transaction', error, { 
      user_id: req.params.userId
    });
    
    const errorResponse = cryptoErrorHandler.handleError(error, {
      endpoint: '/crypto-portfolio/:userId/transactions',
      dataType: 'transaction_record'
    });
    
    res.status(500).json({
      success: false,
      error: errorResponse
    });
  }
});

module.exports = router;
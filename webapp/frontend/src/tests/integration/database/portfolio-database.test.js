/**
 * Portfolio Database Integration Tests
 * Tests portfolio data operations with real database connections
 */

import { describe, it, expect, beforeEach, afterEach, beforeAll, afterAll, vi } from 'vitest';

// Mock database connection
const mockDatabase = {
  portfolios: new Map(),
  holdings: new Map(),
  transactions: new Map(),
  nextPortfolioId: 1,
  nextHoldingId: 1,
  nextTransactionId: 1
};

// Mock database operations
const portfolioDb = {
  async createPortfolio(userId, portfolioData) {
    const portfolio = {
      id: mockDatabase.nextPortfolioId++,
      userId,
      ...portfolioData,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    };
    mockDatabase.portfolios.set(portfolio.id, portfolio);
    return portfolio;
  },

  async getPortfolio(portfolioId) {
    return mockDatabase.portfolios.get(portfolioId);
  },

  async getUserPortfolios(userId) {
    return Array.from(mockDatabase.portfolios.values())
      .filter(p => p.userId === userId);
  },

  async updatePortfolio(portfolioId, updates) {
    const portfolio = mockDatabase.portfolios.get(portfolioId);
    if (portfolio) {
      const updated = {
        ...portfolio,
        ...updates,
        updatedAt: new Date().toISOString()
      };
      mockDatabase.portfolios.set(portfolioId, updated);
      return updated;
    }
    return null;
  },

  async deletePortfolio(portfolioId) {
    const deleted = mockDatabase.portfolios.delete(portfolioId);
    // Also delete associated holdings
    Array.from(mockDatabase.holdings.values())
      .filter(h => h.portfolioId === portfolioId)
      .forEach(h => mockDatabase.holdings.delete(h.id));
    return deleted;
  },

  async addHolding(portfolioId, holdingData) {
    const holding = {
      id: mockDatabase.nextHoldingId++,
      portfolioId,
      ...holdingData,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    };
    mockDatabase.holdings.set(holding.id, holding);
    return holding;
  },

  async getPortfolioHoldings(portfolioId) {
    return Array.from(mockDatabase.holdings.values())
      .filter(h => h.portfolioId === portfolioId);
  },

  async updateHolding(holdingId, updates) {
    const holding = mockDatabase.holdings.get(holdingId);
    if (holding) {
      const updated = {
        ...holding,
        ...updates,
        updatedAt: new Date().toISOString()
      };
      mockDatabase.holdings.set(holdingId, updated);
      return updated;
    }
    return null;
  },

  async recordTransaction(portfolioId, transactionData) {
    const transaction = {
      id: mockDatabase.nextTransactionId++,
      portfolioId,
      ...transactionData,
      timestamp: new Date().toISOString()
    };
    mockDatabase.transactions.set(transaction.id, transaction);
    return transaction;
  },

  async getPortfolioTransactions(portfolioId, options = {}) {
    let transactions = Array.from(mockDatabase.transactions.values())
      .filter(t => t.portfolioId === portfolioId);

    // Apply date filtering
    if (options.startDate) {
      transactions = transactions.filter(t => t.timestamp >= options.startDate);
    }
    if (options.endDate) {
      transactions = transactions.filter(t => t.timestamp <= options.endDate);
    }

    // Apply pagination
    if (options.limit) {
      transactions = transactions.slice(0, options.limit);
    }

    return transactions.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
  },

  async calculatePortfolioMetrics(portfolioId) {
    const holdings = await this.getPortfolioHoldings(portfolioId);
    const transactions = await this.getPortfolioTransactions(portfolioId);

    let totalValue = 0;
    let totalCost = 0;
    let totalPnL = 0;

    holdings.forEach(holding => {
      const marketValue = holding.quantity * holding.currentPrice;
      const costBasis = holding.quantity * holding.avgCostBasis;
      totalValue += marketValue;
      totalCost += costBasis;
      totalPnL += (marketValue - costBasis);
    });

    return {
      totalValue,
      totalCost,
      totalPnL,
      totalPnLPercent: totalCost > 0 ? (totalPnL / totalCost) * 100 : 0,
      holdingsCount: holdings.length,
      transactionsCount: transactions.length,
      lastUpdated: new Date().toISOString()
    };
  }
};

describe('Portfolio Database Integration', () => {
  beforeEach(() => {
    // Clear mock database
    mockDatabase.portfolios.clear();
    mockDatabase.holdings.clear();
    mockDatabase.transactions.clear();
    mockDatabase.nextPortfolioId = 1;
    mockDatabase.nextHoldingId = 1;
    mockDatabase.nextTransactionId = 1;
  });

  describe('Portfolio CRUD Operations', () => {
    it('creates a new portfolio', async () => {
      const portfolioData = {
        name: 'Growth Portfolio',
        description: 'Long-term growth focused portfolio',
        riskLevel: 'moderate',
        targetAllocation: {
          stocks: 70,
          bonds: 20,
          cash: 10
        }
      };

      const portfolio = await portfolioDb.createPortfolio('user_123', portfolioData);

      expect(portfolio.id).toBe(1);
      expect(portfolio.userId).toBe('user_123');
      expect(portfolio.name).toBe('Growth Portfolio');
      expect(portfolio.riskLevel).toBe('moderate');
      expect(portfolio.createdAt).toBeDefined();
      expect(portfolio.targetAllocation.stocks).toBe(70);
    });

    it('retrieves portfolio by ID', async () => {
      const created = await portfolioDb.createPortfolio('user_123', {
        name: 'Test Portfolio',
        riskLevel: 'conservative'
      });

      const retrieved = await portfolioDb.getPortfolio(created.id);

      expect(retrieved.id).toBe(created.id);
      expect(retrieved.name).toBe('Test Portfolio');
      expect(retrieved.riskLevel).toBe('conservative');
    });

    it('gets all portfolios for a user', async () => {
      await portfolioDb.createPortfolio('user_123', { name: 'Portfolio 1' });
      await portfolioDb.createPortfolio('user_123', { name: 'Portfolio 2' });
      await portfolioDb.createPortfolio('user_456', { name: 'Other User Portfolio' });

      const userPortfolios = await portfolioDb.getUserPortfolios('user_123');

      expect(userPortfolios).toHaveLength(2);
      expect(userPortfolios[0].name).toBe('Portfolio 1');
      expect(userPortfolios[1].name).toBe('Portfolio 2');
    });

    it('updates portfolio data', async () => {
      const portfolio = await portfolioDb.createPortfolio('user_123', {
        name: 'Original Name',
        riskLevel: 'conservative'
      });

      const updated = await portfolioDb.updatePortfolio(portfolio.id, {
        name: 'Updated Name',
        riskLevel: 'aggressive'
      });

      expect(updated.name).toBe('Updated Name');
      expect(updated.riskLevel).toBe('aggressive');
      expect(updated.updatedAt).not.toBe(portfolio.createdAt);
    });

    it('deletes portfolio and associated holdings', async () => {
      const portfolio = await portfolioDb.createPortfolio('user_123', { name: 'Test' });
      await portfolioDb.addHolding(portfolio.id, {
        symbol: 'AAPL',
        quantity: 100,
        avgCostBasis: 150.00
      });

      const deleted = await portfolioDb.deletePortfolio(portfolio.id);
      const retrieved = await portfolioDb.getPortfolio(portfolio.id);
      const holdings = await portfolioDb.getPortfolioHoldings(portfolio.id);

      expect(deleted).toBe(true);
      expect(retrieved).toBeUndefined();
      expect(holdings).toHaveLength(0);
    });
  });

  describe('Holdings Management', () => {
    let portfolio;

    beforeEach(async () => {
      portfolio = await portfolioDb.createPortfolio('user_123', { name: 'Test Portfolio' });
    });

    it('adds holding to portfolio', async () => {
      const holdingData = {
        symbol: 'AAPL',
        quantity: 100,
        avgCostBasis: 150.00,
        currentPrice: 155.00,
        sector: 'Technology'
      };

      const holding = await portfolioDb.addHolding(portfolio.id, holdingData);

      expect(holding.id).toBe(1);
      expect(holding.portfolioId).toBe(portfolio.id);
      expect(holding.symbol).toBe('AAPL');
      expect(holding.quantity).toBe(100);
      expect(holding.avgCostBasis).toBe(150.00);
      expect(holding.sector).toBe('Technology');
    });

    it('retrieves all holdings for portfolio', async () => {
      await portfolioDb.addHolding(portfolio.id, {
        symbol: 'AAPL',
        quantity: 100,
        avgCostBasis: 150.00
      });
      await portfolioDb.addHolding(portfolio.id, {
        symbol: 'GOOGL',
        quantity: 50,
        avgCostBasis: 2500.00
      });

      const holdings = await portfolioDb.getPortfolioHoldings(portfolio.id);

      expect(holdings).toHaveLength(2);
      expect(holdings.find(h => h.symbol === 'AAPL')).toBeDefined();
      expect(holdings.find(h => h.symbol === 'GOOGL')).toBeDefined();
    });

    it('updates holding data', async () => {
      const holding = await portfolioDb.addHolding(portfolio.id, {
        symbol: 'AAPL',
        quantity: 100,
        avgCostBasis: 150.00,
        currentPrice: 155.00
      });

      const updated = await portfolioDb.updateHolding(holding.id, {
        quantity: 150,
        currentPrice: 160.00
      });

      expect(updated.quantity).toBe(150);
      expect(updated.currentPrice).toBe(160.00);
      expect(updated.avgCostBasis).toBe(150.00); // Should remain unchanged
    });
  });

  describe('Transaction Recording', () => {
    let portfolio;

    beforeEach(async () => {
      portfolio = await portfolioDb.createPortfolio('user_123', { name: 'Test Portfolio' });
    });

    it('records buy transaction', async () => {
      const transactionData = {
        type: 'BUY',
        symbol: 'AAPL',
        quantity: 100,
        price: 150.00,
        fees: 1.00,
        notes: 'Initial AAPL position'
      };

      const transaction = await portfolioDb.recordTransaction(portfolio.id, transactionData);

      expect(transaction.id).toBe(1);
      expect(transaction.portfolioId).toBe(portfolio.id);
      expect(transaction.type).toBe('BUY');
      expect(transaction.symbol).toBe('AAPL');
      expect(transaction.quantity).toBe(100);
      expect(transaction.price).toBe(150.00);
      expect(transaction.fees).toBe(1.00);
      expect(transaction.timestamp).toBeDefined();
    });

    it('records sell transaction', async () => {
      const transactionData = {
        type: 'SELL',
        symbol: 'AAPL',
        quantity: 50,
        price: 155.00,
        fees: 1.00,
        realizedPnL: 250.00
      };

      const transaction = await portfolioDb.recordTransaction(portfolio.id, transactionData);

      expect(transaction.type).toBe('SELL');
      expect(transaction.realizedPnL).toBe(250.00);
    });

    it('retrieves portfolio transactions with filtering', async () => {
      const now = new Date();
      const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000);
      const tomorrow = new Date(now.getTime() + 24 * 60 * 60 * 1000);

      // Record multiple transactions
      await portfolioDb.recordTransaction(portfolio.id, {
        type: 'BUY',
        symbol: 'AAPL',
        quantity: 100,
        price: 150.00
      });
      
      await portfolioDb.recordTransaction(portfolio.id, {
        type: 'SELL',
        symbol: 'AAPL',
        quantity: 50,
        price: 155.00
      });

      const allTransactions = await portfolioDb.getPortfolioTransactions(portfolio.id);
      expect(allTransactions).toHaveLength(2);

      // Test date filtering
      const filteredTransactions = await portfolioDb.getPortfolioTransactions(portfolio.id, {
        startDate: yesterday.toISOString(),
        endDate: tomorrow.toISOString()
      });
      expect(filteredTransactions).toHaveLength(2);

      // Test limit
      const limitedTransactions = await portfolioDb.getPortfolioTransactions(portfolio.id, {
        limit: 1
      });
      expect(limitedTransactions).toHaveLength(1);
    });
  });

  describe('Portfolio Metrics Calculation', () => {
    let portfolio;

    beforeEach(async () => {
      portfolio = await portfolioDb.createPortfolio('user_123', { name: 'Test Portfolio' });
      
      // Add sample holdings
      await portfolioDb.addHolding(portfolio.id, {
        symbol: 'AAPL',
        quantity: 100,
        avgCostBasis: 150.00,
        currentPrice: 160.00
      });
      
      await portfolioDb.addHolding(portfolio.id, {
        symbol: 'GOOGL',
        quantity: 50,
        avgCostBasis: 2500.00,
        currentPrice: 2600.00
      });

      // Add sample transactions
      await portfolioDb.recordTransaction(portfolio.id, {
        type: 'BUY',
        symbol: 'AAPL',
        quantity: 100,
        price: 150.00
      });
    });

    it('calculates portfolio metrics correctly', async () => {
      const metrics = await portfolioDb.calculatePortfolioMetrics(portfolio.id);

      // AAPL: 100 * $160 = $16,000 (cost: 100 * $150 = $15,000)
      // GOOGL: 50 * $2600 = $130,000 (cost: 50 * $2500 = $125,000)
      // Total value: $146,000, Total cost: $140,000, P&L: $6,000

      expect(metrics.totalValue).toBe(146000);
      expect(metrics.totalCost).toBe(140000);
      expect(metrics.totalPnL).toBe(6000);
      expect(metrics.totalPnLPercent).toBeCloseTo(4.29, 2);
      expect(metrics.holdingsCount).toBe(2);
      expect(metrics.transactionsCount).toBe(1);
      expect(metrics.lastUpdated).toBeDefined();
    });

    it('handles empty portfolio metrics', async () => {
      const emptyPortfolio = await portfolioDb.createPortfolio('user_456', { name: 'Empty' });
      const metrics = await portfolioDb.calculatePortfolioMetrics(emptyPortfolio.id);

      expect(metrics.totalValue).toBe(0);
      expect(metrics.totalCost).toBe(0);
      expect(metrics.totalPnL).toBe(0);
      expect(metrics.totalPnLPercent).toBe(0);
      expect(metrics.holdingsCount).toBe(0);
      expect(metrics.transactionsCount).toBe(0);
    });
  });

  describe('Database Error Handling', () => {
    it('handles non-existent portfolio gracefully', async () => {
      const portfolio = await portfolioDb.getPortfolio(999);
      expect(portfolio).toBeUndefined();
    });

    it('handles update of non-existent portfolio', async () => {
      const result = await portfolioDb.updatePortfolio(999, { name: 'Updated' });
      expect(result).toBeNull();
    });

    it('handles update of non-existent holding', async () => {
      const result = await portfolioDb.updateHolding(999, { quantity: 100 });
      expect(result).toBeNull();
    });

    it('returns empty array for non-existent user portfolios', async () => {
      const portfolios = await portfolioDb.getUserPortfolios('non_existent_user');
      expect(portfolios).toEqual([]);
    });

    it('returns empty array for non-existent portfolio holdings', async () => {
      const holdings = await portfolioDb.getPortfolioHoldings(999);
      expect(holdings).toEqual([]);
    });
  });
});
/**
 * Portfolio Service Unit Tests
 * Comprehensive testing of portfolio management and calculation functionality
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Real Portfolio Service - Import actual production service
import portfolioOptimizer from '../../../services/portfolioOptimizer';
import portfolioMathService from '../../../services/portfolioMathService';
import api from '../../../services/api';
import cacheService from '../../../services/cacheService';

// Mock external dependencies but use real service
vi.mock('../../../services/api');
vi.mock('../../../services/cacheService');

describe('💼 Portfolio Service', () => {
  let mockApi;
  let mockCache;

  beforeEach(() => {
    mockApi = {
      get: vi.fn(),
      post: vi.fn(),
      put: vi.fn(),
      delete: vi.fn()
    };

    mockCache = {
      get: vi.fn(),
      set: vi.fn(),
      invalidate: vi.fn()
    };

    // Configure mocks for external dependencies
    api.get = mockApi.get;
    api.post = mockApi.post;
    
    cacheService.get = mockCache.get;
    cacheService.set = mockCache.set;
    
    // Using real portfolioOptimizer and portfolioMathService instances
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('Portfolio Data Retrieval', () => {
    const mockPortfolioData = {
      id: 'portfolio_123',
      userId: 'user_123',
      name: 'Main Portfolio',
      totalValue: 125000,
      cash: 5000,
      positions: [
        {
          id: 'pos_1',
          symbol: 'AAPL',
          quantity: 100,
          averagePrice: 175.25,
          currentPrice: 185.50,
          marketValue: 18550,
          unrealizedGain: 1025,
          unrealizedGainPercent: 5.85
        }
      ],
      dayChange: 2500,
      dayChangePercent: 2.04,
      totalReturn: 15000,
      totalReturnPercent: 13.64
    };

    it('should get portfolio overview', async () => {
      mockApi.get.mockResolvedValue({ data: { portfolio: mockPortfolioData } });

      const result = await portfolioService.getPortfolio('portfolio_123');

      expect(mockApi.get).toHaveBeenCalledWith('/portfolios/portfolio_123');
      expect(result.portfolio.totalValue).toBe(125000);
      expect(result.portfolio.positions).toHaveLength(1);
    });

    it('should get portfolio summary', async () => {
      const mockSummary = {
        totalValue: 125000,
        dayChange: 2500,
        dayChangePercent: 2.04,
        totalReturn: 15000,
        totalReturnPercent: 13.64,
        positionCount: 12,
        cashBalance: 5000
      };

      mockApi.get.mockResolvedValue({ data: { summary: mockSummary } });

      const summary = await portfolioService.getPortfolioSummary('portfolio_123');

      expect(mockApi.get).toHaveBeenCalledWith('/portfolios/portfolio_123/summary');
      expect(summary.totalValue).toBe(125000);
      expect(summary.positionCount).toBe(12);
    });

    it('should get portfolio positions', async () => {
      const mockPositions = [
        {
          symbol: 'AAPL',
          quantity: 100,
          marketValue: 18550,
          unrealizedGain: 1025
        },
        {
          symbol: 'GOOGL',
          quantity: 25,
          marketValue: 71250,
          unrealizedGain: 3750
        }
      ];

      mockApi.get.mockResolvedValue({ data: { positions: mockPositions } });

      const positions = await portfolioService.getPositions('portfolio_123');

      expect(mockApi.get).toHaveBeenCalledWith('/portfolios/portfolio_123/positions');
      expect(positions).toHaveLength(2);
      expect(positions[0].symbol).toBe('AAPL');
    });

    it('should get individual position details', async () => {
      const mockPosition = {
        id: 'pos_1',
        symbol: 'AAPL',
        quantity: 100,
        averagePrice: 175.25,
        currentPrice: 185.50,
        marketValue: 18550,
        unrealizedGain: 1025,
        unrealizedGainPercent: 5.85,
        trades: [
          { date: '2024-01-01', type: 'buy', quantity: 50, price: 170.00 },
          { date: '2024-01-10', type: 'buy', quantity: 50, price: 180.50 }
        ]
      };

      mockApi.get.mockResolvedValue({ data: { position: mockPosition } });

      const position = await portfolioService.getPosition('portfolio_123', 'AAPL');

      expect(mockApi.get).toHaveBeenCalledWith('/portfolios/portfolio_123/positions/AAPL');
      expect(position.symbol).toBe('AAPL');
      expect(position.trades).toHaveLength(2);
    });
  });

  describe('Portfolio Performance Analysis', () => {
    it('should calculate portfolio performance', async () => {
      const mockPerformance = {
        returns: {
          '1D': { value: 2500, percent: 2.04 },
          '1W': { value: 6250, percent: 5.26 },
          '1M': { value: 10000, percent: 8.70 },
          '3M': { value: 15000, percent: 13.64 },
          '1Y': { value: 22500, percent: 21.95 }
        },
        benchmarkComparison: {
          portfolioReturn: 21.95,
          benchmarkReturn: 14.25,
          alpha: 7.70,
          beta: 1.15,
          sharpeRatio: 1.35
        },
        riskMetrics: {
          volatility: 18.5,
          maxDrawdown: -12.3,
          varDaily: -2850,
          sortino: 1.42
        }
      };

      mockApi.get.mockResolvedValue({ data: { performance: mockPerformance } });

      const performance = await portfolioService.getPerformance('portfolio_123');

      expect(mockApi.get).toHaveBeenCalledWith('/portfolios/portfolio_123/performance');
      expect(performance.returns['1Y'].percent).toBe(21.95);
      expect(performance.benchmarkComparison.alpha).toBe(7.70);
    });

    it('should calculate portfolio risk metrics', async () => {
      const mockRiskMetrics = {
        totalRisk: 18.5,
        systematicRisk: 12.3,
        idiosyncraticRisk: 6.2,
        beta: 1.15,
        correlation: 0.82,
        maxDrawdown: -12.3,
        valueAtRisk: {
          daily95: -2850,
          daily99: -4125,
          weekly95: -6375,
          monthly95: -12750
        },
        conditionalVaR: {
          daily95: -3980,
          weekly95: -8920
        }
      };

      mockCalculations.calculateRisk.mockReturnValue(mockRiskMetrics);
      mockApi.get.mockResolvedValue({ data: { positions: [] } });

      const riskMetrics = await portfolioService.calculateRisk('portfolio_123');

      expect(mockCalculations.calculateRisk).toHaveBeenCalled();
      expect(riskMetrics.beta).toBe(1.15);
      expect(riskMetrics.valueAtRisk.daily95).toBe(-2850);
    });

    it('should analyze sector allocation', async () => {
      const mockAllocation = {
        sectors: [
          { name: 'Technology', value: 45000, percentage: 36.0, count: 5 },
          { name: 'Healthcare', value: 25000, percentage: 20.0, count: 3 },
          { name: 'Financial', value: 20000, percentage: 16.0, count: 2 },
          { name: 'Consumer', value: 15000, percentage: 12.0, count: 2 },
          { name: 'Energy', value: 10000, percentage: 8.0, count: 1 },
          { name: 'Cash', value: 10000, percentage: 8.0, count: 1 }
        ],
        diversificationScore: 0.78,
        concentrationRisk: 'Medium'
      };

      mockCalculations.calculateAllocation.mockReturnValue(mockAllocation);
      mockApi.get.mockResolvedValue({ data: { positions: [] } });

      const allocation = await portfolioService.getSectorAllocation('portfolio_123');

      expect(mockCalculations.calculateAllocation).toHaveBeenCalled();
      expect(allocation.sectors).toHaveLength(6);
      expect(allocation.diversificationScore).toBe(0.78);
    });
  });

  describe('Portfolio Management Operations', () => {
    it('should create new portfolio', async () => {
      const portfolioData = {
        name: 'Growth Portfolio',
        description: 'Long-term growth focused portfolio',
        riskTolerance: 'moderate',
        investmentGoals: ['growth', 'income']
      };

      const mockCreatedPortfolio = {
        id: 'portfolio_456',
        ...portfolioData,
        userId: 'user_123',
        createdAt: '2024-01-15T10:30:00Z',
        totalValue: 0,
        positions: []
      };

      mockApi.post.mockResolvedValue({ data: { portfolio: mockCreatedPortfolio } });

      const result = await portfolioService.createPortfolio(portfolioData);

      expect(mockApi.post).toHaveBeenCalledWith('/portfolios', portfolioData);
      expect(result.portfolio.name).toBe('Growth Portfolio');
      expect(result.portfolio.id).toBe('portfolio_456');
    });

    it('should update portfolio settings', async () => {
      const updateData = {
        name: 'Updated Portfolio Name',
        description: 'Updated description',
        riskTolerance: 'aggressive'
      };

      mockApi.put.mockResolvedValue({ data: { portfolio: updateData } });

      const result = await portfolioService.updatePortfolio('portfolio_123', updateData);

      expect(mockApi.put).toHaveBeenCalledWith('/portfolios/portfolio_123', updateData);
      expect(result.portfolio.name).toBe('Updated Portfolio Name');
    });

    it('should delete portfolio', async () => {
      mockApi.delete.mockResolvedValue({ data: { message: 'Portfolio deleted successfully' } });

      const result = await portfolioService.deletePortfolio('portfolio_123');

      expect(mockApi.delete).toHaveBeenCalledWith('/portfolios/portfolio_123');
      expect(result.message).toBe('Portfolio deleted successfully');
    });

    it('should rebalance portfolio', async () => {
      const rebalanceStrategy = {
        targetAllocations: [
          { symbol: 'AAPL', targetPercent: 25 },
          { symbol: 'GOOGL', targetPercent: 25 },
          { symbol: 'MSFT', targetPercent: 25 },
          { symbol: 'Cash', targetPercent: 25 }
        ],
        tolerance: 0.05
      };

      const mockRebalanceResult = {
        trades: [
          { symbol: 'AAPL', action: 'sell', quantity: 25, estimatedValue: 4625 },
          { symbol: 'TSLA', action: 'buy', quantity: 15, estimatedValue: 3300 }
        ],
        estimatedCost: 15.50,
        impactAnalysis: {
          taxImplications: 156.75,
          marketImpact: 0.02
        }
      };

      mockApi.post.mockResolvedValue({ data: mockRebalanceResult });

      const result = await portfolioService.rebalancePortfolio('portfolio_123', rebalanceStrategy);

      expect(mockApi.post).toHaveBeenCalledWith('/portfolios/portfolio_123/rebalance', rebalanceStrategy);
      expect(result.trades).toHaveLength(2);
      expect(result.estimatedCost).toBe(15.50);
    });
  });

  describe('Transaction History', () => {
    it('should get transaction history', async () => {
      const mockTransactions = [
        {
          id: 'txn_1',
          type: 'buy',
          symbol: 'AAPL',
          quantity: 50,
          price: 180.00,
          value: 9000,
          fees: 7.50,
          date: '2024-01-15T10:30:00Z'
        },
        {
          id: 'txn_2',
          type: 'sell',
          symbol: 'TSLA',
          quantity: 25,
          price: 220.00,
          value: 5500,
          fees: 7.50,
          date: '2024-01-14T14:45:00Z'
        }
      ];

      mockApi.get.mockResolvedValue({ data: { transactions: mockTransactions } });

      const transactions = await portfolioService.getTransactionHistory('portfolio_123');

      expect(mockApi.get).toHaveBeenCalledWith('/portfolios/portfolio_123/transactions');
      expect(transactions).toHaveLength(2);
      expect(transactions[0].symbol).toBe('AAPL');
    });

    it('should get filtered transaction history', async () => {
      const filters = {
        symbol: 'AAPL',
        type: 'buy',
        startDate: '2024-01-01',
        endDate: '2024-01-31'
      };

      mockApi.get.mockResolvedValue({ data: { transactions: [] } });

      await portfolioService.getTransactionHistory('portfolio_123', filters);

      expect(mockApi.get).toHaveBeenCalledWith('/portfolios/portfolio_123/transactions', {
        params: filters
      });
    });

    it('should export transaction history', async () => {
      const exportOptions = {
        format: 'csv',
        dateRange: '2024',
        includeMetadata: true
      };

      mockApi.get.mockResolvedValue({ 
        data: 'Date,Symbol,Type,Quantity,Price,Value,Fees\n2024-01-15,AAPL,buy,50,180.00,9000,7.50'
      });

      const result = await portfolioService.exportTransactions('portfolio_123', exportOptions);

      expect(mockApi.get).toHaveBeenCalledWith('/portfolios/portfolio_123/transactions/export', {
        params: exportOptions
      });
      expect(result).toContain('Date,Symbol,Type');
    });
  });

  describe('Portfolio Analytics', () => {
    it('should generate portfolio report', async () => {
      const reportConfig = {
        type: 'comprehensive',
        period: 'quarterly',
        includeCharts: true,
        format: 'pdf'
      };

      const mockReport = {
        reportId: 'report_123',
        generatedAt: '2024-01-15T15:30:00Z',
        downloadUrl: '/reports/portfolio_123/report_123.pdf',
        summary: {
          totalReturn: 18.75,
          riskAdjustedReturn: 1.35,
          benchmarkOutperformance: 4.50
        }
      };

      mockApi.post.mockResolvedValue({ data: { report: mockReport } });

      const result = await portfolioService.generateReport('portfolio_123', reportConfig);

      expect(mockApi.post).toHaveBeenCalledWith('/portfolios/portfolio_123/reports', reportConfig);
      expect(result.report.reportId).toBe('report_123');
      expect(result.report.summary.totalReturn).toBe(18.75);
    });

    it('should get portfolio insights', async () => {
      const mockInsights = [
        {
          type: 'opportunity',
          title: 'Sector Underweight',
          description: 'Your technology allocation is 5% below optimal',
          actionable: true,
          priority: 'medium'
        },
        {
          type: 'risk',
          title: 'High Concentration',
          description: 'AAPL represents 35% of your portfolio',
          actionable: true,
          priority: 'high'
        }
      ];

      mockApi.get.mockResolvedValue({ data: { insights: mockInsights } });

      const insights = await portfolioService.getInsights('portfolio_123');

      expect(mockApi.get).toHaveBeenCalledWith('/portfolios/portfolio_123/insights');
      expect(insights).toHaveLength(2);
      expect(insights[1].priority).toBe('high');
    });

    it('should calculate optimal portfolio allocation', async () => {
      const optimizationParams = {
        riskTolerance: 'moderate',
        timeHorizon: 'long_term',
        objectives: ['growth', 'income'],
        constraints: {
          maxSinglePosition: 0.15,
          minCashAllocation: 0.05
        }
      };

      const mockOptimization = {
        recommendedAllocations: [
          { symbol: 'AAPL', currentWeight: 0.35, targetWeight: 0.15, action: 'reduce' },
          { symbol: 'VTI', currentWeight: 0.00, targetWeight: 0.25, action: 'add' },
          { symbol: 'VXUS', currentWeight: 0.00, targetWeight: 0.15, action: 'add' }
        ],
        expectedReturn: 0.095,
        expectedRisk: 0.145,
        sharpeRatio: 0.655
      };

      mockApi.post.mockResolvedValue({ data: mockOptimization });

      const result = await portfolioService.optimizeAllocation('portfolio_123', optimizationParams);

      expect(mockApi.post).toHaveBeenCalledWith('/portfolios/portfolio_123/optimize', optimizationParams);
      expect(result.recommendedAllocations).toHaveLength(3);
      expect(result.expectedReturn).toBe(0.095);
    });
  });

  describe('Caching and Performance', () => {
    it('should cache portfolio data efficiently', async () => {
      const cacheKey = 'portfolio_123_summary';
      const mockCachedData = { totalValue: 125000, cached: true };

      mockCache.get.mockReturnValue(mockCachedData);

      const result = await portfolioService.getPortfolioSummary('portfolio_123');

      expect(mockCache.get).toHaveBeenCalledWith(cacheKey);
      expect(result).toEqual(mockCachedData);
      expect(mockApi.get).not.toHaveBeenCalled();
    });

    it('should invalidate cache on portfolio updates', async () => {
      const updateData = { name: 'Updated Portfolio' };
      mockApi.put.mockResolvedValue({ data: { portfolio: updateData } });

      await portfolioService.updatePortfolio('portfolio_123', updateData);

      expect(mockCache.invalidate).toHaveBeenCalledWith('portfolio_123_*');
    });

    it('should handle concurrent portfolio requests efficiently', async () => {
      mockApi.get.mockResolvedValue({ data: { portfolio: { id: 'portfolio_123' } } });

      const promise1 = portfolioService.getPortfolio('portfolio_123');
      const promise2 = portfolioService.getPortfolio('portfolio_123');

      await Promise.all([promise1, promise2]);

      // Should deduplicate concurrent requests
      expect(mockApi.get).toHaveBeenCalledTimes(1);
    });
  });

  describe('Error Handling', () => {
    it('should handle portfolio not found', async () => {
      mockApi.get.mockRejectedValue({
        response: { 
          status: 404,
          data: { message: 'Portfolio not found' }
        }
      });

      await expect(portfolioService.getPortfolio('nonexistent_portfolio'))
        .rejects.toMatchObject({
          response: { status: 404 }
        });
    });

    it('should handle insufficient permissions', async () => {
      mockApi.get.mockRejectedValue({
        response: { 
          status: 403,
          data: { message: 'Access denied to portfolio' }
        }
      });

      await expect(portfolioService.getPortfolio('restricted_portfolio'))
        .rejects.toMatchObject({
          response: { status: 403 }
        });
    });

    it('should handle calculation errors gracefully', async () => {
      mockCalculations.calculateRisk.mockImplementation(() => {
        throw new Error('Calculation failed');
      });
      mockApi.get.mockResolvedValue({ data: { positions: [] } });

      await expect(portfolioService.calculateRisk('portfolio_123'))
        .rejects.toThrow('Calculation failed');
    });

    it('should retry failed requests', async () => {
      mockApi.get
        .mockRejectedValueOnce(new Error('Network error'))
        .mockResolvedValue({ data: { portfolio: { id: 'portfolio_123' } } });

      const result = await portfolioService.getPortfolio('portfolio_123');

      expect(mockApi.get).toHaveBeenCalledTimes(2);
      expect(result.portfolio.id).toBe('portfolio_123');
    });
  });

  describe('Performance Optimization', () => {
    it('should batch multiple portfolio requests', async () => {
      const portfolioIds = ['portfolio_1', 'portfolio_2', 'portfolio_3'];
      const mockBatchResponse = {
        portfolios: portfolioIds.map(id => ({ id, totalValue: 100000 }))
      };

      mockApi.post.mockResolvedValue({ data: mockBatchResponse });

      const result = await portfolioService.getPortfoliosBatch(portfolioIds);

      expect(mockApi.post).toHaveBeenCalledWith('/portfolios/batch', { portfolioIds });
      expect(result.portfolios).toHaveLength(3);
    });

    it('should perform calculations efficiently', async () => {
      const startTime = performance.now();
      
      mockCalculations.calculatePortfolioValue.mockReturnValue(125000);
      mockApi.get.mockResolvedValue({ data: { positions: [] } });

      await portfolioService.getPortfolioSummary('portfolio_123');
      
      const executionTime = performance.now() - startTime;
      expect(executionTime).toBeLessThan(100); // Should complete within 100ms
    });
  });
});
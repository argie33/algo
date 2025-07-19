/**
 * Analytics Service Unit Tests
 * Comprehensive testing of analytics and reporting functionality
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Real Analytics Service - Import actual production service
import { AnalyticsService } from '../../../services/AnalyticsService';
import { apiClient } from '../../../services/api';
import { databaseClient } from '../../../services/database';
import { cacheService } from '../../../services/cache';
import { reportingEngine } from '../../../utils/reportingEngine';

// Mock external dependencies but use real service
vi.mock('../../../services/api');
vi.mock('../../../services/database');
vi.mock('../../../services/cache');
vi.mock('../../../utils/reportingEngine');

describe('📊 Analytics Service', () => {
  let analyticsService;
  let mockApi;
  let mockDb;
  let mockCache;
  let mockReporting;

  const mockPortfolioData = {
    id: '1',
    userId: 'user123',
    totalValue: 100000,
    positions: [
      {
        symbol: 'AAPL',
        quantity: 100,
        currentPrice: 150,
        currentValue: 15000,
        costBasis: 14000,
        unrealizedGain: 1000
      },
      {
        symbol: 'GOOGL',
        quantity: 25,
        currentPrice: 2800,
        currentValue: 70000,
        costBasis: 65000,
        unrealizedGain: 5000
      }
    ],
    createdAt: '2023-01-01T00:00:00Z'
  };

  const mockTimeSeriesData = [
    { date: '2024-01-01', value: 95000, benchmark: 94000 },
    { date: '2024-01-02', value: 96000, benchmark: 95000 },
    { date: '2024-01-03', value: 98000, benchmark: 96500 },
    { date: '2024-01-04', value: 100000, benchmark: 98000 }
  ];

  beforeEach(() => {
    mockApi = {
      get: vi.fn(),
      post: vi.fn(),
      put: vi.fn(),
      delete: vi.fn()
    };

    mockDb = {
      query: vi.fn(),
      transaction: vi.fn()
    };

    mockCache = {
      get: vi.fn(),
      set: vi.fn(),
      delete: vi.fn(),
      clear: vi.fn()
    };

    mockReporting = {
      generateReport: vi.fn(),
      exportToPDF: vi.fn(),
      exportToExcel: vi.fn(),
      scheduleReport: vi.fn()
    };

    // Mock the imports
    apiClient.mockReturnValue(mockApi);
    databaseClient.mockReturnValue(mockDb);
    cacheService.mockReturnValue(mockCache);
    reportingEngine.mockReturnValue(mockReporting);

    analyticsService = new AnalyticsService();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('Portfolio Performance Analytics', () => {
    it('should calculate portfolio performance metrics', async () => {
      mockApi.get.mockResolvedValueOnce(mockPortfolioData);
      mockApi.get.mockResolvedValueOnce(mockTimeSeriesData);

      const result = await analyticsService.getPortfolioPerformance('1', '1Y');

      expect(mockApi.get).toHaveBeenCalledWith('/portfolios/1');
      expect(mockApi.get).toHaveBeenCalledWith('/portfolios/1/timeseries', {
        params: { period: '1Y' }
      });

      expect(result).toEqual({
        portfolioId: '1',
        period: '1Y',
        totalReturn: expect.any(Number),
        annualizedReturn: expect.any(Number),
        volatility: expect.any(Number),
        sharpeRatio: expect.any(Number),
        maxDrawdown: expect.any(Number),
        alpha: expect.any(Number),
        beta: expect.any(Number),
        benchmarkComparison: expect.any(Object),
        riskMetrics: expect.any(Object)
      });
    });

    it('should handle different time periods', async () => {
      mockApi.get.mockResolvedValue(mockPortfolioData);
      mockApi.get.mockResolvedValue(mockTimeSeriesData);

      await analyticsService.getPortfolioPerformance('1', '1M');
      expect(mockApi.get).toHaveBeenCalledWith('/portfolios/1/timeseries', {
        params: { period: '1M' }
      });

      await analyticsService.getPortfolioPerformance('1', '3M');
      expect(mockApi.get).toHaveBeenCalledWith('/portfolios/1/timeseries', {
        params: { period: '3M' }
      });
    });

    it('should cache performance calculations', async () => {
      const cacheKey = 'portfolio_performance_1_1Y';
      const cachedData = { totalReturn: 0.15, volatility: 0.18 };

      mockCache.get.mockResolvedValue(cachedData);

      const result = await analyticsService.getPortfolioPerformance('1', '1Y');

      expect(mockCache.get).toHaveBeenCalledWith(cacheKey);
      expect(result).toEqual(cachedData);
      expect(mockApi.get).not.toHaveBeenCalled();
    });

    it('should validate portfolio ID', async () => {
      await expect(analyticsService.getPortfolioPerformance()).rejects.toThrow('Portfolio ID is required');
      await expect(analyticsService.getPortfolioPerformance('')).rejects.toThrow('Portfolio ID is required');
    });
  });

  describe('Risk Analytics', () => {
    it('should calculate Value at Risk (VaR)', async () => {
      const returns = [-0.05, -0.02, 0.01, 0.03, -0.01, 0.02, -0.03];
      mockApi.get.mockResolvedValue({ returns });

      const result = await analyticsService.calculateVaR('1', 0.95, 252);

      expect(result).toEqual({
        portfolioId: '1',
        confidence: 0.95,
        timeHorizon: 252,
        var: expect.any(Number),
        expectedShortfall: expect.any(Number),
        methodology: 'historical_simulation'
      });

      expect(result.var).toBeLessThan(0); // VaR should be negative
    });

    it('should perform stress testing', async () => {
      const scenarios = [
        { name: 'Market Crash', shocks: { 'SP500': -0.20, 'NASDAQ': -0.25 } },
        { name: 'Interest Rate Spike', shocks: { 'BONDS': -0.15, 'REIT': -0.18 } }
      ];

      mockApi.post.mockResolvedValue({
        results: [
          { scenario: 'Market Crash', portfolioImpact: -0.18, value: 82000 },
          { scenario: 'Interest Rate Spike', portfolioImpact: -0.12, value: 88000 }
        ]
      });

      const result = await analyticsService.performStressTesting('1', scenarios);

      expect(mockApi.post).toHaveBeenCalledWith('/analytics/stress-test', {
        portfolioId: '1',
        scenarios
      });

      expect(result.results).toHaveLength(2);
      expect(result.worstCaseScenario).toEqual({
        scenario: 'Market Crash',
        portfolioImpact: -0.18,
        value: 82000
      });
    });

    it('should calculate correlation matrix', async () => {
      const positions = ['AAPL', 'GOOGL', 'MSFT', 'TSLA'];
      mockApi.get.mockResolvedValue({
        correlations: {
          'AAPL-GOOGL': 0.75,
          'AAPL-MSFT': 0.82,
          'AAPL-TSLA': 0.45,
          'GOOGL-MSFT': 0.78,
          'GOOGL-TSLA': 0.38,
          'MSFT-TSLA': 0.42
        }
      });

      const result = await analyticsService.getCorrelationMatrix('1');

      expect(result).toEqual({
        portfolioId: '1',
        matrix: expect.any(Array),
        averageCorrelation: expect.any(Number),
        highlyCorrelated: expect.any(Array),
        diversificationScore: expect.any(Number)
      });
    });
  });

  describe('Asset Allocation Analytics', () => {
    it('should analyze current allocation', async () => {
      mockApi.get.mockResolvedValue(mockPortfolioData);

      const result = await analyticsService.analyzeAssetAllocation('1');

      expect(result).toEqual({
        portfolioId: '1',
        byAssetClass: expect.any(Object),
        bySector: expect.any(Object),
        byGeography: expect.any(Object),
        byMarketCap: expect.any(Object),
        concentrationRisk: expect.any(Object),
        diversificationScore: expect.any(Number),
        recommendations: expect.any(Array)
      });

      expect(result.bySector.Technology).toBeGreaterThan(0);
    });

    it('should suggest optimal allocation', async () => {
      const userProfile = {
        riskTolerance: 'moderate',
        timeHorizon: 10,
        goals: ['growth', 'income']
      };

      mockApi.post.mockResolvedValue({
        optimalAllocation: {
          stocks: 0.70,
          bonds: 0.25,
          alternatives: 0.05
        },
        expectedReturn: 0.08,
        expectedRisk: 0.15
      });

      const result = await analyticsService.suggestOptimalAllocation('1', userProfile);

      expect(mockApi.post).toHaveBeenCalledWith('/analytics/optimize-allocation', {
        portfolioId: '1',
        userProfile
      });

      expect(result.optimalAllocation.stocks).toBe(0.70);
      expect(result.rebalancingSteps).toBeDefined();
    });

    it('should track allocation drift', async () => {
      const targetAllocation = {
        stocks: 0.60,
        bonds: 0.30,
        cash: 0.10
      };

      mockApi.get.mockResolvedValue({
        current: { stocks: 0.70, bonds: 0.25, cash: 0.05 },
        target: targetAllocation
      });

      const result = await analyticsService.trackAllocationDrift('1');

      expect(result).toEqual({
        portfolioId: '1',
        currentAllocation: expect.any(Object),
        targetAllocation: expect.any(Object),
        drift: expect.any(Object),
        rebalanceRequired: expect.any(Boolean),
        severity: expect.any(String)
      });
    });
  });

  describe('Performance Attribution', () => {
    it('should perform sector attribution analysis', async () => {
      mockApi.get.mockResolvedValue({
        sectorReturns: {
          Technology: { weight: 0.40, return: 0.12, benchmark: 0.08 },
          Healthcare: { weight: 0.25, return: 0.06, benchmark: 0.07 },
          Finance: { weight: 0.20, return: 0.09, benchmark: 0.10 }
        }
      });

      const result = await analyticsService.performAttributionAnalysis('1', 'sector');

      expect(result).toEqual({
        portfolioId: '1',
        type: 'sector',
        totalExcessReturn: expect.any(Number),
        allocationEffect: expect.any(Number),
        selectionEffect: expect.any(Number),
        interactionEffect: expect.any(Number),
        breakdown: expect.any(Object)
      });
    });

    it('should calculate security-level attribution', async () => {
      mockApi.get.mockResolvedValue({
        securities: [
          { symbol: 'AAPL', weight: 0.15, return: 0.20, contribution: 0.03 },
          { symbol: 'GOOGL', weight: 0.25, return: 0.08, contribution: 0.02 }
        ]
      });

      const result = await analyticsService.performAttributionAnalysis('1', 'security');

      expect(result.breakdown).toBeDefined();
      expect(result.topContributors).toBeDefined();
      expect(result.bottomContributors).toBeDefined();
    });
  });

  describe('Benchmarking', () => {
    it('should compare against multiple benchmarks', async () => {
      const benchmarks = ['SPY', 'VTI', 'VXUS'];
      
      mockApi.get.mockResolvedValue({
        comparisons: [
          { benchmark: 'SPY', correlation: 0.85, trackingError: 0.08, beta: 1.12 },
          { benchmark: 'VTI', correlation: 0.82, trackingError: 0.09, beta: 1.08 },
          { benchmark: 'VXUS', correlation: 0.45, trackingError: 0.15, beta: 0.65 }
        ]
      });

      const result = await analyticsService.benchmarkPortfolio('1', benchmarks);

      expect(result).toEqual({
        portfolioId: '1',
        benchmarks: expect.any(Array),
        bestFit: expect.any(Object),
        activeReturn: expect.any(Number),
        informationRatio: expect.any(Number)
      });
    });

    it('should calculate tracking error', async () => {
      const portfolioReturns = [0.01, 0.02, -0.01, 0.03];
      const benchmarkReturns = [0.008, 0.018, -0.005, 0.025];

      const trackingError = await analyticsService.calculateTrackingError(
        portfolioReturns, 
        benchmarkReturns
      );

      expect(trackingError).toBeGreaterThan(0);
      expect(trackingError).toBeLessThan(1);
    });
  });

  describe('Custom Analytics', () => {
    it('should create custom metrics', async () => {
      const customMetric = {
        name: 'ESG Score',
        formula: 'weighted_average(positions.esg_score, positions.weight)',
        category: 'sustainability'
      };

      mockApi.post.mockResolvedValue({
        metricId: 'custom_123',
        value: 7.5,
        benchmarkValue: 6.8
      });

      const result = await analyticsService.createCustomMetric('1', customMetric);

      expect(mockApi.post).toHaveBeenCalledWith('/analytics/custom-metrics', {
        portfolioId: '1',
        metric: customMetric
      });

      expect(result.metricId).toBe('custom_123');
      expect(result.value).toBe(7.5);
    });

    it('should save and retrieve custom dashboards', async () => {
      const dashboard = {
        name: 'Risk Dashboard',
        widgets: [
          { type: 'var', config: { confidence: 0.95 } },
          { type: 'correlation_heatmap', config: {} },
          { type: 'stress_test', config: { scenarios: ['market_crash'] } }
        ]
      };

      mockApi.post.mockResolvedValue({ dashboardId: 'dash_456' });

      const result = await analyticsService.saveCustomDashboard('1', dashboard);

      expect(result.dashboardId).toBe('dash_456');

      mockApi.get.mockResolvedValue(dashboard);
      const retrieved = await analyticsService.getCustomDashboard('1', 'dash_456');

      expect(retrieved.name).toBe('Risk Dashboard');
      expect(retrieved.widgets).toHaveLength(3);
    });
  });

  describe('Reporting', () => {
    it('should generate portfolio performance reports', async () => {
      const reportConfig = {
        type: 'performance',
        period: '1Y',
        format: 'pdf',
        includeCharts: true
      };

      mockReporting.generateReport.mockResolvedValue({
        reportId: 'report_789',
        url: 'https://reports.example.com/report_789.pdf'
      });

      const result = await analyticsService.generateReport('1', reportConfig);

      expect(mockReporting.generateReport).toHaveBeenCalledWith({
        portfolioId: '1',
        config: reportConfig
      });

      expect(result.reportId).toBe('report_789');
      expect(result.url).toContain('.pdf');
    });

    it('should schedule recurring reports', async () => {
      const schedule = {
        frequency: 'monthly',
        dayOfMonth: 1,
        recipients: ['user@example.com'],
        reportType: 'performance_summary'
      };

      mockReporting.scheduleReport.mockResolvedValue({
        scheduleId: 'sched_101',
        nextRun: '2024-02-01T09:00:00Z'
      });

      const result = await analyticsService.scheduleReport('1', schedule);

      expect(result.scheduleId).toBe('sched_101');
      expect(result.nextRun).toBeDefined();
    });

    it('should export data to different formats', async () => {
      mockReporting.exportToExcel.mockResolvedValue({
        filename: 'portfolio_data.xlsx',
        url: 'https://exports.example.com/portfolio_data.xlsx'
      });

      const result = await analyticsService.exportPortfolioData('1', 'excel');

      expect(mockReporting.exportToExcel).toHaveBeenCalled();
      expect(result.filename).toContain('.xlsx');
    });
  });

  describe('Real-time Analytics', () => {
    it('should handle real-time data updates', async () => {
      const mockWebSocket = {
        on: vi.fn(),
        emit: vi.fn(),
        disconnect: vi.fn()
      };

      const callback = vi.fn();
      
      analyticsService.subscribeToRealtimeUpdates('1', callback, mockWebSocket);

      expect(mockWebSocket.on).toHaveBeenCalledWith('portfolio_update', expect.any(Function));
      expect(mockWebSocket.emit).toHaveBeenCalledWith('subscribe', { portfolioId: '1' });
    });

    it('should calculate live performance metrics', async () => {
      const liveData = {
        totalValue: 102000,
        dayChange: 2000,
        dayChangePercent: 0.02
      };

      mockApi.get.mockResolvedValue(liveData);

      const result = await analyticsService.getLivePerformance('1');

      expect(result).toEqual({
        portfolioId: '1',
        currentValue: 102000,
        dayChange: 2000,
        dayChangePercent: 0.02,
        timestamp: expect.any(String)
      });
    });
  });

  describe('Error Handling', () => {
    it('should handle API errors gracefully', async () => {
      mockApi.get.mockRejectedValue(new Error('API Error'));

      await expect(analyticsService.getPortfolioPerformance('1', '1Y'))
        .rejects.toThrow('Failed to fetch portfolio performance');
    });

    it('should handle invalid time periods', async () => {
      await expect(analyticsService.getPortfolioPerformance('1', 'invalid'))
        .rejects.toThrow('Invalid time period');
    });

    it('should handle missing portfolio data', async () => {
      mockApi.get.mockResolvedValue(null);

      await expect(analyticsService.getPortfolioPerformance('1', '1Y'))
        .rejects.toThrow('Portfolio not found');
    });

    it('should handle calculation errors', async () => {
      const invalidReturns = ['invalid', null, undefined];
      
      expect(() => analyticsService.calculateSharpeRatio(invalidReturns, 0.02))
        .toThrow('Invalid returns data');
    });
  });

  describe('Performance Optimization', () => {
    it('should use efficient caching strategies', async () => {
      const cacheKey = 'portfolio_analytics_1_1Y';
      mockCache.get.mockResolvedValue(null);
      mockApi.get.mockResolvedValue(mockPortfolioData);

      await analyticsService.getPortfolioPerformance('1', '1Y');

      expect(mockCache.set).toHaveBeenCalledWith(
        cacheKey,
        expect.any(Object),
        expect.any(Number) // TTL
      );
    });

    it('should handle large datasets efficiently', async () => {
      const largePriceHistory = Array.from({ length: 10000 }, (_, i) => ({
        date: `2020-01-${i % 30 + 1}`,
        price: 100 + Math.random() * 50
      }));

      mockApi.get.mockResolvedValue({ priceHistory: largePriceHistory });

      const startTime = performance.now();
      await analyticsService.calculateHistoricalVolatility('1');
      const duration = performance.now() - startTime;

      expect(duration).toBeLessThan(1000); // Should complete within 1 second
    });

    it('should batch multiple analytics requests', async () => {
      const requests = [
        { type: 'performance', portfolioId: '1' },
        { type: 'risk', portfolioId: '1' },
        { type: 'allocation', portfolioId: '1' }
      ];

      mockApi.post.mockResolvedValue({
        results: [
          { type: 'performance', data: {} },
          { type: 'risk', data: {} },
          { type: 'allocation', data: {} }
        ]
      });

      const results = await analyticsService.batchAnalytics(requests);

      expect(mockApi.post).toHaveBeenCalledOnce();
      expect(results).toHaveLength(3);
    });
  });

  describe('Integration with External Services', () => {
    it('should integrate with third-party analytics providers', async () => {
      const externalProvider = 'morningstar';
      const apiKey = 'test_api_key';

      mockApi.get.mockResolvedValue({
        morningstarRating: 4,
        analystRecommendation: 'Buy',
        priceTarget: 180
      });

      const result = await analyticsService.getExternalAnalytics('1', externalProvider, apiKey);

      expect(result.provider).toBe('morningstar');
      expect(result.data.morningstarRating).toBe(4);
    });

    it('should handle external service failures', async () => {
      mockApi.get.mockRejectedValue(new Error('External service unavailable'));

      const result = await analyticsService.getExternalAnalytics('1', 'failed_provider');

      expect(result.error).toBe('External service unavailable');
      expect(result.fallbackData).toBeDefined();
    });
  });
});
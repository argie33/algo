/**
 * Unit tests for Advanced Performance Analytics
 */

const { AdvancedPerformanceAnalytics } = require('../../../utils/advancedPerformanceAnalytics');

describe('AdvancedPerformanceAnalytics', () => {
  let analytics;
  let mockDb;

  beforeEach(() => {
    mockDb = {
      query: jest.fn()
    };
    analytics = new AdvancedPerformanceAnalytics(mockDb);
  });

  describe('calculateBaseMetrics', () => {
    test('calculates basic performance metrics correctly', async () => {
      const portfolioHistory = [
        { date: '2024-01-01', total_value: '100000' },
        { date: '2024-01-02', total_value: '105000' },
        { date: '2024-01-03', total_value: '110000' }
      ];

      const metrics = await analytics.calculateBaseMetrics(portfolioHistory);

      expect(metrics.totalReturn).toBe(10000);
      expect(metrics.totalReturnPercent).toBe(10);
      expect(metrics.startValue).toBe(100000);
      expect(metrics.endValue).toBe(110000);
      expect(metrics.dailyReturns).toHaveLength(2);
    });

    test('handles empty portfolio history', async () => {
      const metrics = await analytics.calculateBaseMetrics([]);

      expect(metrics.totalReturn).toBe(0);
      expect(metrics.annualizedReturn).toBe(0);
      expect(metrics.totalReturnPercent).toBe(0);
    });
  });

  describe('calculateRiskMetrics', () => {
    test('calculates risk metrics correctly', async () => {
      const portfolioHistory = [
        { total_value: '100000' },
        { total_value: '105000' },
        { total_value: '98000' },
        { total_value: '102000' }
      ];

      const metrics = await analytics.calculateRiskMetrics(portfolioHistory);

      expect(metrics.volatility).toBeGreaterThan(0);
      expect(metrics.maxDrawdown).toBeGreaterThan(0);
      expect(metrics.valueAtRisk).toBeDefined();
      expect(metrics.expectedShortfall).toBeDefined();
    });
  });

  describe('calculateMaxDrawdown', () => {
    test('calculates maximum drawdown correctly', () => {
      const portfolioHistory = [
        { total_value: '100000' },
        { total_value: '120000' },
        { total_value: '90000' },
        { total_value: '110000' }
      ];

      const maxDrawdown = analytics.calculateMaxDrawdown(portfolioHistory);

      expect(maxDrawdown).toBe(25); // 25% drawdown from 120000 to 90000
    });
  });

  describe('calculateAttributionAnalysis', () => {
    test('calculates attribution analysis correctly', async () => {
      const mockHoldings = [
        {
          symbol: 'AAPL',
          sector: 'Technology',
          total_value: '50000',
          total_pnl: '5000',
          total_cost_basis: '45000'
        },
        {
          symbol: 'GOOGL',
          sector: 'Technology',
          total_value: '30000',
          total_pnl: '3000',
          total_cost_basis: '27000'
        }
      ];

      mockDb.query.mockResolvedValue({ rows: mockHoldings });

      const analysis = await analytics.calculateAttributionAnalysis('user123', '2024-01-01', '2024-12-31');

      expect(analysis.totalPortfolioValue).toBe(80000);
      expect(analysis.securityAttribution).toHaveLength(2);
      expect(analysis.sectorAttribution).toHaveLength(1);
      expect(analysis.sectorAttribution[0].sector).toBe('Technology');
    });
  });

  describe('calculateSectorAnalysis', () => {
    test('calculates sector analysis correctly', async () => {
      const mockSectors = [
        {
          sector: 'Technology',
          holding_count: '5',
          total_value: '100000',
          total_pnl: '10000',
          avg_return: '10.5',
          return_volatility: '15.2'
        },
        {
          sector: 'Healthcare',
          holding_count: '3',
          total_value: '50000',
          total_pnl: '2500',
          avg_return: '5.0',
          return_volatility: '12.1'
        }
      ];

      mockDb.query.mockResolvedValue({ rows: mockSectors });

      const analysis = await analytics.calculateSectorAnalysis('user123', '2024-01-01', '2024-12-31');

      expect(analysis.sectorBreakdown).toHaveLength(2);
      expect(analysis.sectorCount).toBe(2);
      expect(analysis.diversificationScore).toBeDefined();
    });
  });

  describe('calculateDiversificationScore', () => {
    test('calculates diversification score correctly', () => {
      const sectors = [
        { total_value: '60000' },
        { total_value: '40000' }
      ];
      const totalValue = 100000;

      const result = analytics.calculateDiversificationScore(sectors, totalValue);

      expect(result.diversificationScore).toBeGreaterThan(0);
      expect(result.diversificationScore).toBeLessThan(100);
      expect(result.herfindahlIndex).toBeDefined();
      expect(result.interpretation).toBeDefined();
    });
  });

  describe('generatePerformanceReport', () => {
    test('generates comprehensive performance report', async () => {
      const mockPortfolioHistory = [
        { date: '2024-01-01', total_value: '100000' },
        { date: '2024-06-01', total_value: '110000' },
        { date: '2024-12-31', total_value: '120000' }
      ];

      mockDb.query.mockResolvedValue({ rows: mockPortfolioHistory });

      const report = await analytics.generatePerformanceReport('user123', '2024-01-01', '2024-12-31');

      expect(report.reportId).toBeDefined();
      expect(report.userId).toBe('user123');
      expect(report.summary).toBeDefined();
      expect(report.metrics).toBeDefined();
      expect(report.recommendations).toBeDefined();
      expect(report.generatedAt).toBeDefined();
    });
  });

  describe('getPerformanceGrade', () => {
    test('assigns correct performance grades', () => {
      expect(analytics.getPerformanceGrade(25)).toBe('A+');
      expect(analytics.getPerformanceGrade(18)).toBe('A');
      expect(analytics.getPerformanceGrade(12)).toBe('B+');
      expect(analytics.getPerformanceGrade(7)).toBe('B');
      expect(analytics.getPerformanceGrade(2)).toBe('C');
      expect(analytics.getPerformanceGrade(-2)).toBe('D');
      expect(analytics.getPerformanceGrade(-10)).toBe('F');
    });
  });

  describe('assessRiskProfile', () => {
    test('assesses risk profile correctly', () => {
      expect(analytics.assessRiskProfile({ volatility: 30, maxDrawdown: 25 })).toBe('High Risk');
      expect(analytics.assessRiskProfile({ volatility: 18, maxDrawdown: 12 })).toBe('Medium Risk');
      expect(analytics.assessRiskProfile({ volatility: 10, maxDrawdown: 5 })).toBe('Low Risk');
    });
  });

  describe('calculateDaysInPeriod', () => {
    test('calculates days in period correctly', () => {
      const days = analytics.calculateDaysInPeriod('2024-01-01', '2024-01-31');
      expect(days).toBe(30);
    });
  });
});
/**
 * Risk Service Unit Tests
 * Comprehensive testing of risk assessment and management functionality
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock external dependencies
vi.mock('../../../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn()
}));

vi.mock('../../../utils/calculations', () => ({
  calculateVolatility: vi.fn(),
  calculateBeta: vi.fn(),
  calculateVaR: vi.fn(),
  calculateSharpeRatio: vi.fn()
}));

// Mock Risk Service
class RiskService {
  constructor(apiClient, calculationUtils) {
    this.api = apiClient;
    this.calc = calculationUtils;
    this.riskThresholds = {
      conservative: { maxVolatility: 0.15, maxBeta: 0.8, maxVaR: 0.05 },
      moderate: { maxVolatility: 0.25, maxBeta: 1.2, maxVaR: 0.08 },
      aggressive: { maxVolatility: 0.40, maxBeta: 1.8, maxVaR: 0.12 }
    };
  }

  async assessPortfolioRisk(portfolioId, riskProfile = 'moderate') {
    if (!portfolioId) {
      throw new Error('Portfolio ID is required');
    }

    if (!this.isValidRiskProfile(riskProfile)) {
      throw new Error('Invalid risk profile');
    }

    try {
      const portfolio = await this.api.get(`/portfolios/${portfolioId}`);
      const positions = await this.api.get(`/portfolios/${portfolioId}/positions`);
      const marketData = await this.api.get(`/portfolios/${portfolioId}/market-data`);

      const assessment = await this.calculateRiskMetrics(portfolio, positions, marketData);
      const compliance = this.checkRiskCompliance(assessment, riskProfile);
      const recommendations = this.generateRiskRecommendations(assessment, compliance);

      return {
        portfolioId,
        riskProfile,
        assessment,
        compliance,
        recommendations,
        timestamp: new Date().toISOString()
      };
    } catch (error) {
      throw this.handleRiskError(error);
    }
  }

  async calculateRiskMetrics(portfolio, positions, marketData) {
    const portfolioValue = portfolio.totalValue;
    const returns = this.calculatePortfolioReturns(positions, marketData);
    
    const volatility = this.calc.calculateVolatility(returns);
    const beta = this.calc.calculateBeta(returns, marketData.benchmarkReturns);
    const var95 = this.calc.calculateVaR(returns, 0.95);
    const var99 = this.calc.calculateVaR(returns, 0.99);
    const sharpeRatio = this.calc.calculateSharpeRatio(returns, 0.02); // 2% risk-free rate

    const concentration = this.calculateConcentrationRisk(positions, portfolioValue);
    const correlation = this.calculateCorrelationRisk(positions, marketData);
    const liquidity = this.calculateLiquidityRisk(positions);
    const currency = this.calculateCurrencyRisk(positions);

    return {
      volatility,
      beta,
      valueAtRisk: {
        var95,
        var99,
        expectedShortfall: this.calculateExpectedShortfall(returns, 0.95)
      },
      sharpeRatio,
      concentration,
      correlation,
      liquidity,
      currency,
      overallRiskScore: this.calculateOverallRiskScore({
        volatility, beta, var95, concentration, correlation, liquidity
      })
    };
  }

  calculatePortfolioReturns(positions, marketData) {
    const portfolioReturns = [];
    const totalValue = positions.reduce((sum, p) => sum + p.currentValue, 0);

    for (let i = 0; i < marketData.historicalData.length; i++) {
      let dailyReturn = 0;
      
      positions.forEach(position => {
        const weight = position.currentValue / totalValue;
        const symbolData = marketData.historicalData[i][position.symbol];
        if (symbolData) {
          dailyReturn += weight * symbolData.dailyReturn;
        }
      });
      
      portfolioReturns.push(dailyReturn);
    }

    return portfolioReturns;
  }

  calculateConcentrationRisk(positions, totalValue) {
    const sectorAllocations = {};
    const positionWeights = [];

    positions.forEach(position => {
      const weight = position.currentValue / totalValue;
      positionWeights.push(weight);

      const sector = position.sector || 'Unknown';
      sectorAllocations[sector] = (sectorAllocations[sector] || 0) + weight;
    });

    const maxPositionWeight = Math.max(...positionWeights);
    const maxSectorWeight = Math.max(...Object.values(sectorAllocations));
    const herfindahlIndex = positionWeights.reduce((sum, w) => sum + w * w, 0);

    return {
      maxPositionWeight,
      maxSectorWeight,
      herfindahlIndex,
      sectorAllocations,
      riskLevel: this.assessConcentrationRiskLevel(maxPositionWeight, maxSectorWeight, herfindahlIndex)
    };
  }

  calculateCorrelationRisk(positions, marketData) {
    const correlations = [];
    
    for (let i = 0; i < positions.length; i++) {
      for (let j = i + 1; j < positions.length; j++) {
        const symbol1 = positions[i].symbol;
        const symbol2 = positions[j].symbol;
        
        const correlation = this.calculateCorrelation(
          marketData.correlationMatrix[symbol1],
          marketData.correlationMatrix[symbol2]
        );
        
        correlations.push({
          pair: [symbol1, symbol2],
          correlation,
          riskLevel: Math.abs(correlation) > 0.7 ? 'high' : Math.abs(correlation) > 0.5 ? 'medium' : 'low'
        });
      }
    }

    const avgCorrelation = correlations.reduce((sum, c) => sum + Math.abs(c.correlation), 0) / correlations.length;
    
    return {
      averageCorrelation: avgCorrelation,
      highCorrelationPairs: correlations.filter(c => Math.abs(c.correlation) > 0.7),
      correlationMatrix: correlations,
      riskLevel: avgCorrelation > 0.6 ? 'high' : avgCorrelation > 0.4 ? 'medium' : 'low'
    };
  }

  calculateLiquidityRisk(positions) {
    const liquidityScores = positions.map(position => ({
      symbol: position.symbol,
      averageVolume: position.averageVolume || 0,
      marketCap: position.marketCap || 0,
      bidAskSpread: position.bidAskSpread || 0,
      liquidityScore: this.calculateLiquidityScore(position),
      liquidityRisk: this.assessLiquidityRisk(position)
    }));

    const avgLiquidityScore = liquidityScores.reduce((sum, s) => sum + s.liquidityScore, 0) / liquidityScores.length;
    const illiquidPositions = liquidityScores.filter(s => s.liquidityRisk === 'high');

    return {
      averageLiquidityScore: avgLiquidityScore,
      illiquidPositions,
      liquidityByPosition: liquidityScores,
      overallLiquidityRisk: this.assessOverallLiquidityRisk(avgLiquidityScore, illiquidPositions)
    };
  }

  calculateCurrencyRisk(positions) {
    const currencyExposure = {};
    const totalValue = positions.reduce((sum, p) => sum + p.currentValue, 0);

    positions.forEach(position => {
      const currency = position.currency || 'USD';
      currencyExposure[currency] = (currencyExposure[currency] || 0) + (position.currentValue / totalValue);
    });

    const nonBaseCurrencyExposure = Object.entries(currencyExposure)
      .filter(([currency]) => currency !== 'USD')
      .reduce((sum, [, exposure]) => sum + exposure, 0);

    return {
      currencyExposure,
      nonBaseCurrencyExposure,
      riskLevel: nonBaseCurrencyExposure > 0.3 ? 'high' : nonBaseCurrencyExposure > 0.1 ? 'medium' : 'low'
    };
  }

  calculateOverallRiskScore(metrics) {
    // Weighted risk score calculation
    const weights = {
      volatility: 0.25,
      beta: 0.20,
      var95: 0.20,
      concentration: 0.15,
      correlation: 0.10,
      liquidity: 0.10
    };

    let score = 0;
    
    // Normalize and weight each metric
    score += this.normalizeVolatility(metrics.volatility) * weights.volatility;
    score += this.normalizeBeta(metrics.beta) * weights.beta;
    score += this.normalizeVaR(metrics.var95) * weights.var95;
    score += this.normalizeConcentration(metrics.concentration) * weights.concentration;
    score += this.normalizeCorrelation(metrics.correlation) * weights.correlation;
    score += this.normalizeLiquidity(metrics.liquidity) * weights.liquidity;

    return Math.min(Math.max(score, 0), 1); // Clamp between 0 and 1
  }

  checkRiskCompliance(assessment, riskProfile) {
    const thresholds = this.riskThresholds[riskProfile];
    const violations = [];

    if (assessment.volatility > thresholds.maxVolatility) {
      violations.push({
        metric: 'volatility',
        current: assessment.volatility,
        threshold: thresholds.maxVolatility,
        severity: 'high'
      });
    }

    if (assessment.beta > thresholds.maxBeta) {
      violations.push({
        metric: 'beta',
        current: assessment.beta,
        threshold: thresholds.maxBeta,
        severity: 'medium'
      });
    }

    if (Math.abs(assessment.valueAtRisk.var95) > thresholds.maxVaR) {
      violations.push({
        metric: 'valueAtRisk',
        current: Math.abs(assessment.valueAtRisk.var95),
        threshold: thresholds.maxVaR,
        severity: 'high'
      });
    }

    if (assessment.concentration.maxPositionWeight > 0.3) {
      violations.push({
        metric: 'concentration',
        current: assessment.concentration.maxPositionWeight,
        threshold: 0.3,
        severity: 'medium'
      });
    }

    return {
      isCompliant: violations.length === 0,
      violations,
      riskLevel: this.determineRiskLevel(violations),
      lastChecked: new Date().toISOString()
    };
  }

  generateRiskRecommendations(assessment, compliance) {
    const recommendations = [];

    if (!compliance.isCompliant) {
      compliance.violations.forEach(violation => {
        switch (violation.metric) {
          case 'volatility':
            recommendations.push({
              type: 'reduce_volatility',
              priority: 'high',
              description: 'Consider reducing exposure to high-volatility assets',
              actions: [
                'Rebalance portfolio towards lower-volatility securities',
                'Add defensive positions or bonds',
                'Consider volatility hedging strategies'
              ]
            });
            break;

          case 'concentration':
            recommendations.push({
              type: 'diversify',
              priority: 'high',
              description: 'Portfolio is too concentrated in single positions or sectors',
              actions: [
                'Reduce position sizes for largest holdings',
                'Diversify across different sectors',
                'Consider adding international exposure'
              ]
            });
            break;

          case 'valueAtRisk':
            recommendations.push({
              type: 'reduce_var',
              priority: 'high',
              description: 'Value at Risk exceeds acceptable levels',
              actions: [
                'Implement stop-loss orders',
                'Add hedging instruments',
                'Reduce overall portfolio leverage'
              ]
            });
            break;
        }
      });
    }

    // General recommendations based on assessment
    if (assessment.correlation.averageCorrelation > 0.6) {
      recommendations.push({
        type: 'reduce_correlation',
        priority: 'medium',
        description: 'Holdings are highly correlated, reducing diversification benefits',
        actions: [
          'Add uncorrelated asset classes',
          'Consider alternative investments',
          'Implement pairs trading strategies'
        ]
      });
    }

    if (assessment.liquidity.overallLiquidityRisk === 'high') {
      recommendations.push({
        type: 'improve_liquidity',
        priority: 'medium',
        description: 'Portfolio has significant liquidity risk',
        actions: [
          'Increase cash reserves',
          'Replace illiquid positions with liquid alternatives',
          'Establish credit facilities for emergencies'
        ]
      });
    }

    return recommendations;
  }

  async getVaRBacktest(portfolioId, timeframe = '1Y') {
    if (!portfolioId) {
      throw new Error('Portfolio ID is required');
    }

    try {
      const backtestData = await this.api.get(`/risk/var-backtest/${portfolioId}`, {
        params: { timeframe }
      });

      return this.processVaRBacktest(backtestData);
    } catch (error) {
      throw this.handleRiskError(error);
    }
  }

  async getStressTesting(portfolioId, scenarios) {
    if (!portfolioId) {
      throw new Error('Portfolio ID is required');
    }

    if (!scenarios || !Array.isArray(scenarios)) {
      throw new Error('Stress test scenarios are required');
    }

    try {
      const results = await this.api.post(`/risk/stress-test/${portfolioId}`, {
        scenarios
      });

      return this.processStressTestResults(results);
    } catch (error) {
      throw this.handleRiskError(error);
    }
  }

  async updateRiskLimits(portfolioId, limits) {
    if (!portfolioId) {
      throw new Error('Portfolio ID is required');
    }

    this.validateRiskLimits(limits);

    try {
      const updated = await this.api.put(`/risk/limits/${portfolioId}`, limits);
      return updated;
    } catch (error) {
      throw this.handleRiskError(error);
    }
  }

  // Helper methods
  isValidRiskProfile(profile) {
    return ['conservative', 'moderate', 'aggressive'].includes(profile);
  }

  calculateCorrelation(returns1, returns2) {
    if (!returns1 || !returns2 || returns1.length !== returns2.length) {
      return 0;
    }

    const n = returns1.length;
    const mean1 = returns1.reduce((sum, r) => sum + r, 0) / n;
    const mean2 = returns2.reduce((sum, r) => sum + r, 0) / n;

    let numerator = 0;
    let sum1Sq = 0;
    let sum2Sq = 0;

    for (let i = 0; i < n; i++) {
      const diff1 = returns1[i] - mean1;
      const diff2 = returns2[i] - mean2;
      numerator += diff1 * diff2;
      sum1Sq += diff1 * diff1;
      sum2Sq += diff2 * diff2;
    }

    const denominator = Math.sqrt(sum1Sq * sum2Sq);
    return denominator === 0 ? 0 : numerator / denominator;
  }

  calculateExpectedShortfall(returns, confidence) {
    const sortedReturns = returns.slice().sort((a, b) => a - b);
    const tailIndex = Math.floor((1 - confidence) * sortedReturns.length);
    const tailReturns = sortedReturns.slice(0, tailIndex);
    
    return tailReturns.reduce((sum, r) => sum + r, 0) / tailReturns.length;
  }

  calculateLiquidityScore(position) {
    const volumeScore = Math.min(position.averageVolume / 1000000, 1); // Normalize to millions
    const marketCapScore = Math.min(position.marketCap / 10000000000, 1); // Normalize to 10B
    const spreadScore = Math.max(0, 1 - (position.bidAskSpread || 0) * 100); // Invert spread

    return (volumeScore + marketCapScore + spreadScore) / 3;
  }

  assessLiquidityRisk(position) {
    const score = this.calculateLiquidityScore(position);
    if (score > 0.7) return 'low';
    if (score > 0.4) return 'medium';
    return 'high';
  }

  assessConcentrationRiskLevel(maxPosition, maxSector, herfindahl) {
    if (maxPosition > 0.3 || maxSector > 0.4 || herfindahl > 0.25) return 'high';
    if (maxPosition > 0.2 || maxSector > 0.3 || herfindahl > 0.15) return 'medium';
    return 'low';
  }

  assessOverallLiquidityRisk(avgScore, illiquidPositions) {
    if (avgScore < 0.4 || illiquidPositions.length > 3) return 'high';
    if (avgScore < 0.6 || illiquidPositions.length > 1) return 'medium';
    return 'low';
  }

  normalizeVolatility(volatility) {
    return Math.min(volatility / 0.5, 1); // Cap at 50% volatility
  }

  normalizeBeta(beta) {
    return Math.min(Math.abs(beta) / 2, 1); // Cap at beta of 2
  }

  normalizeVaR(var95) {
    return Math.min(Math.abs(var95) / 0.2, 1); // Cap at 20% VaR
  }

  normalizeConcentration(concentration) {
    return concentration.maxPositionWeight; // Already between 0 and 1
  }

  normalizeCorrelation(correlation) {
    return correlation.averageCorrelation; // Already between 0 and 1
  }

  normalizeLiquidity(liquidity) {
    return 1 - liquidity.averageLiquidityScore; // Invert (lower liquidity = higher risk)
  }

  determineRiskLevel(violations) {
    const highSeverityCount = violations.filter(v => v.severity === 'high').length;
    const mediumSeverityCount = violations.filter(v => v.severity === 'medium').length;

    if (highSeverityCount > 0) return 'high';
    if (mediumSeverityCount > 2) return 'high';
    if (mediumSeverityCount > 0) return 'medium';
    return 'low';
  }

  processVaRBacktest(data) {
    return {
      breaches: data.breaches,
      breachRate: data.breaches.length / data.totalObservations,
      expectedBreachRate: 0.05, // 5% for 95% VaR
      isAccurate: Math.abs(data.breaches.length / data.totalObservations - 0.05) < 0.02,
      backtestResults: data.results
    };
  }

  processStressTestResults(results) {
    return {
      scenarios: results.scenarios.map(scenario => ({
        name: scenario.name,
        description: scenario.description,
        portfolioImpact: scenario.impact,
        worstCaseValue: scenario.worstCaseValue,
        expectedLoss: scenario.expectedLoss,
        riskLevel: this.assessScenarioRiskLevel(scenario.impact)
      })),
      overallWorstCase: results.overallWorstCase,
      recommendations: this.generateStressTestRecommendations(results)
    };
  }

  assessScenarioRiskLevel(impact) {
    if (Math.abs(impact) > 0.3) return 'severe';
    if (Math.abs(impact) > 0.15) return 'high';
    if (Math.abs(impact) > 0.05) return 'medium';
    return 'low';
  }

  generateStressTestRecommendations(results) {
    const recommendations = [];
    
    results.scenarios.forEach(scenario => {
      if (Math.abs(scenario.impact) > 0.2) {
        recommendations.push({
          scenario: scenario.name,
          recommendation: `Consider hedging against ${scenario.name} risk`,
          urgency: 'high'
        });
      }
    });

    return recommendations;
  }

  validateRiskLimits(limits) {
    if (!limits || typeof limits !== 'object') {
      throw new Error('Risk limits must be an object');
    }

    if (limits.maxVolatility && (limits.maxVolatility < 0 || limits.maxVolatility > 1)) {
      throw new Error('Max volatility must be between 0 and 1');
    }

    if (limits.maxVaR && (limits.maxVaR < 0 || limits.maxVaR > 1)) {
      throw new Error('Max VaR must be between 0 and 1');
    }

    if (limits.maxPositionSize && (limits.maxPositionSize < 0 || limits.maxPositionSize > 1)) {
      throw new Error('Max position size must be between 0 and 1');
    }
  }

  handleRiskError(error) {
    if (error.response?.status === 404) {
      return new Error('Portfolio not found');
    }

    if (error.response?.status === 403) {
      return new Error('Access denied to risk data');
    }

    if (error.response?.data?.message) {
      return new Error(error.response.data.message);
    }

    return new Error(error.message || 'Risk service error');
  }
}

describe('⚠️ Risk Service', () => {
  let riskService;
  let mockApi;
  let mockCalc;

  const mockPortfolio = {
    id: '1',
    totalValue: 100000,
    cashBalance: 5000
  };

  const mockPositions = [
    {
      symbol: 'AAPL',
      currentValue: 40000,
      sector: 'Technology',
      currency: 'USD',
      averageVolume: 50000000,
      marketCap: 2500000000000,
      bidAskSpread: 0.001
    },
    {
      symbol: 'GOOGL',
      currentValue: 30000,
      sector: 'Technology',
      currency: 'USD',
      averageVolume: 25000000,
      marketCap: 1800000000000,
      bidAskSpread: 0.002
    },
    {
      symbol: 'JPM',
      currentValue: 25000,
      sector: 'Financial',
      currency: 'USD',
      averageVolume: 15000000,
      marketCap: 500000000000,
      bidAskSpread: 0.003
    }
  ];

  const mockMarketData = {
    benchmarkReturns: [0.01, -0.005, 0.02, -0.01, 0.015],
    historicalData: [
      { AAPL: { dailyReturn: 0.02 }, GOOGL: { dailyReturn: 0.015 }, JPM: { dailyReturn: 0.01 } },
      { AAPL: { dailyReturn: -0.01 }, GOOGL: { dailyReturn: -0.005 }, JPM: { dailyReturn: 0.005 } },
      { AAPL: { dailyReturn: 0.025 }, GOOGL: { dailyReturn: 0.02 }, JPM: { dailyReturn: 0.015 } }
    ],
    correlationMatrix: {
      AAPL: [0.02, -0.01, 0.025],
      GOOGL: [0.015, -0.005, 0.02],
      JPM: [0.01, 0.005, 0.015]
    }
  };

  beforeEach(() => {
    mockApi = {
      get: vi.fn(),
      post: vi.fn(),
      put: vi.fn()
    };

    mockCalc = {
      calculateVolatility: vi.fn(),
      calculateBeta: vi.fn(),
      calculateVaR: vi.fn(),
      calculateSharpeRatio: vi.fn()
    };

    riskService = new RiskService(mockApi, mockCalc);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('Portfolio Risk Assessment', () => {
    it('should assess portfolio risk successfully', async () => {
      mockApi.get.mockImplementation((url) => {
        if (url.includes('/portfolios/1')) return Promise.resolve(mockPortfolio);
        if (url.includes('/positions')) return Promise.resolve(mockPositions);
        if (url.includes('/market-data')) return Promise.resolve(mockMarketData);
      });

      mockCalc.calculateVolatility.mockReturnValue(0.20);
      mockCalc.calculateBeta.mockReturnValue(1.15);
      mockCalc.calculateVaR.mockReturnValue(-0.08);
      mockCalc.calculateSharpeRatio.mockReturnValue(1.25);

      const result = await riskService.assessPortfolioRisk('1', 'moderate');

      expect(result.portfolioId).toBe('1');
      expect(result.riskProfile).toBe('moderate');
      expect(result.assessment).toBeDefined();
      expect(result.compliance).toBeDefined();
      expect(result.recommendations).toBeDefined();
    });

    it('should validate portfolio ID', async () => {
      await expect(riskService.assessPortfolioRisk()).rejects.toThrow('Portfolio ID is required');
    });

    it('should validate risk profile', async () => {
      await expect(riskService.assessPortfolioRisk('1', 'invalid'))
        .rejects.toThrow('Invalid risk profile');
    });

    it('should check valid risk profiles', () => {
      expect(riskService.isValidRiskProfile('conservative')).toBe(true);
      expect(riskService.isValidRiskProfile('moderate')).toBe(true);
      expect(riskService.isValidRiskProfile('aggressive')).toBe(true);
      expect(riskService.isValidRiskProfile('invalid')).toBe(false);
    });
  });

  describe('Risk Metrics Calculation', () => {
    beforeEach(() => {
      mockCalc.calculateVolatility.mockReturnValue(0.20);
      mockCalc.calculateBeta.mockReturnValue(1.15);
      mockCalc.calculateVaR.mockReturnValue(-0.08);
      mockCalc.calculateSharpeRatio.mockReturnValue(1.25);
    });

    it('should calculate comprehensive risk metrics', async () => {
      const metrics = await riskService.calculateRiskMetrics(mockPortfolio, mockPositions, mockMarketData);

      expect(metrics.volatility).toBe(0.20);
      expect(metrics.beta).toBe(1.15);
      expect(metrics.valueAtRisk.var95).toBe(-0.08);
      expect(metrics.sharpeRatio).toBe(1.25);
      expect(metrics.concentration).toBeDefined();
      expect(metrics.correlation).toBeDefined();
      expect(metrics.liquidity).toBeDefined();
      expect(metrics.currency).toBeDefined();
      expect(metrics.overallRiskScore).toBeGreaterThanOrEqual(0);
      expect(metrics.overallRiskScore).toBeLessThanOrEqual(1);
    });

    it('should calculate portfolio returns correctly', () => {
      const returns = riskService.calculatePortfolioReturns(mockPositions, mockMarketData);

      expect(returns).toHaveLength(3);
      expect(returns[0]).toBeCloseTo(0.0175, 4); // Weighted average
    });

    it('should calculate concentration risk', () => {
      const concentration = riskService.calculateConcentrationRisk(mockPositions, 95000);

      expect(concentration.maxPositionWeight).toBeCloseTo(0.421, 3); // 40000/95000
      expect(concentration.maxSectorWeight).toBeCloseTo(0.737, 3); // Tech: (40000+30000)/95000
      expect(concentration.sectorAllocations.Technology).toBeCloseTo(0.737, 3);
      expect(concentration.sectorAllocations.Financial).toBeCloseTo(0.263, 3);
    });

    it('should calculate liquidity risk', () => {
      const liquidity = riskService.calculateLiquidityRisk(mockPositions);

      expect(liquidity.liquidityByPosition).toHaveLength(3);
      expect(liquidity.averageLiquidityScore).toBeGreaterThan(0);
      expect(liquidity.overallLiquidityRisk).toMatch(/^(low|medium|high)$/);
    });

    it('should calculate currency risk', () => {
      const currency = riskService.calculateCurrencyRisk(mockPositions);

      expect(currency.currencyExposure.USD).toBe(1); // All positions in USD
      expect(currency.nonBaseCurrencyExposure).toBe(0);
      expect(currency.riskLevel).toBe('low');
    });

    it('should assess liquidity risk levels correctly', () => {
      const highLiquidityPosition = {
        averageVolume: 100000000,
        marketCap: 50000000000,
        bidAskSpread: 0.001
      };

      const lowLiquidityPosition = {
        averageVolume: 100000,
        marketCap: 100000000,
        bidAskSpread: 0.05
      };

      expect(riskService.assessLiquidityRisk(highLiquidityPosition)).toBe('low');
      expect(riskService.assessLiquidityRisk(lowLiquidityPosition)).toBe('high');
    });
  });

  describe('Risk Compliance', () => {
    it('should check compliance for conservative profile', () => {
      const assessment = {
        volatility: 0.10,
        beta: 0.7,
        valueAtRisk: { var95: -0.03 },
        concentration: { maxPositionWeight: 0.2 }
      };

      const compliance = riskService.checkRiskCompliance(assessment, 'conservative');

      expect(compliance.isCompliant).toBe(true);
      expect(compliance.violations).toHaveLength(0);
      expect(compliance.riskLevel).toBe('low');
    });

    it('should identify violations for aggressive portfolio', () => {
      const assessment = {
        volatility: 0.45, // Exceeds aggressive threshold of 0.40
        beta: 2.0, // Exceeds aggressive threshold of 1.8
        valueAtRisk: { var95: -0.15 }, // Exceeds aggressive threshold of 0.12
        concentration: { maxPositionWeight: 0.4 } // Exceeds general threshold of 0.3
      };

      const compliance = riskService.checkRiskCompliance(assessment, 'aggressive');

      expect(compliance.isCompliant).toBe(false);
      expect(compliance.violations).toHaveLength(4);
      expect(compliance.riskLevel).toBe('high');
    });

    it('should handle different violation severities', () => {
      const assessment = {
        volatility: 0.30, // Exceeds moderate threshold
        beta: 1.5, // Exceeds moderate threshold
        valueAtRisk: { var95: -0.10 }, // Exceeds moderate threshold
        concentration: { maxPositionWeight: 0.35 } // Exceeds concentration threshold
      };

      const compliance = riskService.checkRiskCompliance(assessment, 'moderate');

      const highSeverityViolations = compliance.violations.filter(v => v.severity === 'high');
      const mediumSeverityViolations = compliance.violations.filter(v => v.severity === 'medium');

      expect(highSeverityViolations.length).toBeGreaterThan(0);
      expect(mediumSeverityViolations.length).toBeGreaterThan(0);
    });
  });

  describe('Risk Recommendations', () => {
    it('should generate recommendations for high volatility', () => {
      const assessment = {
        volatility: 0.35,
        correlation: { averageCorrelation: 0.4 },
        liquidity: { overallLiquidityRisk: 'low' }
      };

      const compliance = {
        isCompliant: false,
        violations: [{ metric: 'volatility', severity: 'high' }]
      };

      const recommendations = riskService.generateRiskRecommendations(assessment, compliance);

      expect(recommendations).toHaveLength(1);
      expect(recommendations[0].type).toBe('reduce_volatility');
      expect(recommendations[0].priority).toBe('high');
      expect(recommendations[0].actions).toContain('Rebalance portfolio towards lower-volatility securities');
    });

    it('should generate recommendations for concentration risk', () => {
      const assessment = {
        correlation: { averageCorrelation: 0.4 },
        liquidity: { overallLiquidityRisk: 'low' }
      };

      const compliance = {
        isCompliant: false,
        violations: [{ metric: 'concentration', severity: 'high' }]
      };

      const recommendations = riskService.generateRiskRecommendations(assessment, compliance);

      expect(recommendations[0].type).toBe('diversify');
      expect(recommendations[0].actions).toContain('Reduce position sizes for largest holdings');
    });

    it('should generate correlation recommendations', () => {
      const assessment = {
        correlation: { averageCorrelation: 0.7 },
        liquidity: { overallLiquidityRisk: 'low' }
      };

      const compliance = { isCompliant: true, violations: [] };

      const recommendations = riskService.generateRiskRecommendations(assessment, compliance);

      expect(recommendations.some(r => r.type === 'reduce_correlation')).toBe(true);
    });

    it('should generate liquidity recommendations', () => {
      const assessment = {
        correlation: { averageCorrelation: 0.4 },
        liquidity: { overallLiquidityRisk: 'high' }
      };

      const compliance = { isCompliant: true, violations: [] };

      const recommendations = riskService.generateRiskRecommendations(assessment, compliance);

      expect(recommendations.some(r => r.type === 'improve_liquidity')).toBe(true);
    });
  });

  describe('VaR Backtesting', () => {
    it('should perform VaR backtest successfully', async () => {
      const mockBacktestData = {
        breaches: [
          { date: '2023-01-15', actualLoss: -0.08, varEstimate: -0.05 },
          { date: '2023-03-10', actualLoss: -0.12, varEstimate: -0.06 }
        ],
        totalObservations: 252,
        results: []
      };

      mockApi.get.mockResolvedValue(mockBacktestData);

      const result = await riskService.getVaRBacktest('1', '1Y');

      expect(mockApi.get).toHaveBeenCalledWith('/risk/var-backtest/1', {
        params: { timeframe: '1Y' }
      });
      expect(result.breaches).toHaveLength(2);
      expect(result.breachRate).toBeCloseTo(0.0079, 4); // 2/252
      expect(result.expectedBreachRate).toBe(0.05);
      expect(result.isAccurate).toBe(true); // Within 2% tolerance
    });
  });

  describe('Stress Testing', () => {
    it('should perform stress testing successfully', async () => {
      const scenarios = [
        { name: 'Market Crash', description: '20% market decline' },
        { name: 'Interest Rate Shock', description: '200bp rate increase' }
      ];

      const mockResults = {
        scenarios: [
          { name: 'Market Crash', impact: -0.18, worstCaseValue: 82000, expectedLoss: 18000 },
          { name: 'Interest Rate Shock', impact: -0.12, worstCaseValue: 88000, expectedLoss: 12000 }
        ],
        overallWorstCase: 82000
      };

      mockApi.post.mockResolvedValue(mockResults);

      const result = await riskService.getStressTesting('1', scenarios);

      expect(mockApi.post).toHaveBeenCalledWith('/risk/stress-test/1', { scenarios });
      expect(result.scenarios).toHaveLength(2);
      expect(result.overallWorstCase).toBe(82000);
    });

    it('should assess scenario risk levels correctly', () => {
      expect(riskService.assessScenarioRiskLevel(-0.35)).toBe('severe');
      expect(riskService.assessScenarioRiskLevel(-0.20)).toBe('high');
      expect(riskService.assessScenarioRiskLevel(-0.10)).toBe('medium');
      expect(riskService.assessScenarioRiskLevel(-0.03)).toBe('low');
    });

    it('should validate stress test scenarios', async () => {
      await expect(riskService.getStressTesting('1', null))
        .rejects.toThrow('Stress test scenarios are required');

      await expect(riskService.getStressTesting('1', 'invalid'))
        .rejects.toThrow('Stress test scenarios are required');
    });
  });

  describe('Risk Limits Management', () => {
    it('should update risk limits successfully', async () => {
      const limits = {
        maxVolatility: 0.25,
        maxVaR: 0.08,
        maxPositionSize: 0.20
      };

      mockApi.put.mockResolvedValue({ success: true, limits });

      const result = await riskService.updateRiskLimits('1', limits);

      expect(mockApi.put).toHaveBeenCalledWith('/risk/limits/1', limits);
      expect(result.success).toBe(true);
    });

    it('should validate risk limits', async () => {
      await expect(riskService.updateRiskLimits('1', null))
        .rejects.toThrow('Risk limits must be an object');

      await expect(riskService.updateRiskLimits('1', { maxVolatility: -0.1 }))
        .rejects.toThrow('Max volatility must be between 0 and 1');

      await expect(riskService.updateRiskLimits('1', { maxVaR: 1.5 }))
        .rejects.toThrow('Max VaR must be between 0 and 1');

      await expect(riskService.updateRiskLimits('1', { maxPositionSize: 2 }))
        .rejects.toThrow('Max position size must be between 0 and 1');
    });
  });

  describe('Correlation Calculations', () => {
    it('should calculate correlation correctly', () => {
      const returns1 = [0.01, -0.02, 0.03, -0.01, 0.02];
      const returns2 = [0.005, -0.015, 0.025, -0.005, 0.015];

      const correlation = riskService.calculateCorrelation(returns1, returns2);

      expect(correlation).toBeGreaterThan(0.8); // Should be highly correlated
      expect(correlation).toBeLessThanOrEqual(1);
    });

    it('should handle invalid correlation inputs', () => {
      expect(riskService.calculateCorrelation(null, [1, 2, 3])).toBe(0);
      expect(riskService.calculateCorrelation([1, 2], [1, 2, 3])).toBe(0);
      expect(riskService.calculateCorrelation([], [])).toBe(0);
    });
  });

  describe('Expected Shortfall', () => {
    it('should calculate expected shortfall correctly', () => {
      const returns = [-0.15, -0.10, -0.08, -0.05, -0.02, 0.01, 0.03, 0.05, 0.08, 0.10];
      const es = riskService.calculateExpectedShortfall(returns, 0.95);

      // Should average the worst 5% of returns
      expect(es).toBeCloseTo(-0.15, 2);
    });
  });

  describe('Risk Score Normalization', () => {
    it('should normalize risk metrics correctly', () => {
      expect(riskService.normalizeVolatility(0.25)).toBe(0.5);
      expect(riskService.normalizeVolatility(0.50)).toBe(1.0);
      expect(riskService.normalizeVolatility(0.75)).toBe(1.0); // Capped

      expect(riskService.normalizeBeta(1.0)).toBe(0.5);
      expect(riskService.normalizeBeta(-1.5)).toBe(0.75);
      expect(riskService.normalizeBeta(3.0)).toBe(1.0); // Capped

      expect(riskService.normalizeVaR(-0.10)).toBe(0.5);
      expect(riskService.normalizeVaR(-0.20)).toBe(1.0);
    });
  });

  describe('Error Handling', () => {
    it('should handle different API errors', () => {
      const error404 = { response: { status: 404 } };
      const error403 = { response: { status: 403 } };
      const errorWithMessage = { response: { data: { message: 'Custom error' } } };

      expect(riskService.handleRiskError(error404).message).toBe('Portfolio not found');
      expect(riskService.handleRiskError(error403).message).toBe('Access denied to risk data');
      expect(riskService.handleRiskError(errorWithMessage).message).toBe('Custom error');
    });

    it('should handle API failures gracefully', async () => {
      mockApi.get.mockRejectedValue(new Error('Network error'));

      await expect(riskService.assessPortfolioRisk('1'))
        .rejects.toThrow('Network error');
    });

    it('should handle missing calculation utilities', async () => {
      mockApi.get.mockImplementation((url) => {
        if (url.includes('/portfolios/1')) return Promise.resolve(mockPortfolio);
        if (url.includes('/positions')) return Promise.resolve(mockPositions);
        if (url.includes('/market-data')) return Promise.resolve(mockMarketData);
      });

      mockCalc.calculateVolatility.mockImplementation(() => {
        throw new Error('Calculation error');
      });

      await expect(riskService.assessPortfolioRisk('1'))
        .rejects.toThrow('Calculation error');
    });
  });
});
/**
 * SWING TRADING PORTFOLIO OPTIMIZER
 *
 * Swing Trading Rules:
 * - Portfolio size: 12-15 best stocks (concentrated)
 * - Position size cap: 1% risk per trade / 7-8% stop loss = ~13% max
 * - Risk management: Stop loss determines position size
 * - Allocation: Score-weighted among top performers
 * - Diversification: Max 3 per sector, min 5 sectors
 */

const { query } = require('./database');

async function generateSwingTradingPortfolio() {
  try {
    console.log('🎯 Generating Swing Trading Portfolio (12-15 best stocks)...');

    // Get top candidates by composite score
    // Using threshold of 50+ to get a meaningful candidate pool (585 stocks available)
    // Only 1 stock exceeds 60, so use 50 as practical minimum
    const candidatesQuery = `
      SELECT
        ss.symbol,
        c.short_name as company_name,
        c.sector,
        ss.composite_score,
        ss.quality_score,
        ss.stability_score,
        ss.growth_score,
        ss.value_score,
        ss.momentum_score,
        (SELECT close FROM price_daily WHERE symbol = ss.symbol ORDER BY date DESC LIMIT 1) as current_price
      FROM stock_scores ss
      LEFT JOIN company_profile c ON ss.symbol = c.ticker
      WHERE ss.composite_score IS NOT NULL AND ss.composite_score > 50
      ORDER BY ss.composite_score DESC
      LIMIT 20
    `;

    const candidatesResult = await query(candidatesQuery);
    const candidates = candidatesResult.rows || [];

    if (candidates.length === 0) {
      console.log('⚠️ No qualified candidates found');
      return { success: false, error: 'No candidates available' };
    }

    console.log(`✅ Found ${candidates.length} candidates, selecting top 12-15...`);

    // Select 12-15 with sector diversification
    const portfolio = selectDiversifiedPortfolio(candidates.slice(0, 20), 12, 15);

    // Calculate position sizes based on risk rules
    const allocations = calculateRiskBasedAllocations(portfolio);

    // Generate trade recommendations
    const recommendations = generateTradeRecommendations(allocations);

    // Calculate portfolio analysis metrics
    const portfolioAnalysis = calculatePortfolioAnalysis(portfolio, allocations);

    // Generate performance attribution for each stock
    const performanceAttribution = generatePerformanceAttribution(portfolio);

    return {
      success: true,
      portfolio: portfolio,
      allocations: allocations,
      recommendations: recommendations,
      portfolioAnalysis: portfolioAnalysis,
      performanceAttribution: performanceAttribution,
      summary: {
        stockCount: portfolio.length,
        totalAllocation: '100%',
        riskMetrics: {
          totalPortfolioRisk: '1% per position',
          maxPosition: '13.3%',
          defaultStopLoss: '7.5%',
          avgRiskReward: '1:1 to 2:1'
        },
        portfolioMetrics: {
          expectedSharpeRatio: portfolioAnalysis.expectedSharpeRatio.toFixed(2),
          portfolioVolatility: portfolioAnalysis.portfolioVolatility.toFixed(2) + '%',
          diversificationScore: portfolioAnalysis.diversificationScore.toFixed(0),
          correlationRisk: portfolioAnalysis.correlationRisk
        }
      }
    };

  } catch (error) {
    console.error('❌ Error in swing trading optimizer:', error);
    return { success: false, error: error.message };
  }
}

function selectDiversifiedPortfolio(candidates, minSize, maxSize) {
  const portfolio = [];
  const sectorCount = new Map();

  // Take top performers with sector constraints
  for (const stock of candidates) {
    if (portfolio.length >= maxSize) break;

    const sector = stock.sector || 'Other';
    const count = sectorCount.get(sector) || 0;

    // Max 3 per sector
    if (count < 3) {
      portfolio.push(stock);
      sectorCount.set(sector, count + 1);
    }
  }

  // Add more if needed to reach minSize
  if (portfolio.length < minSize) {
    for (const stock of candidates) {
      if (!portfolio.find(p => p.symbol === stock.symbol) && portfolio.length < minSize) {
        portfolio.push(stock);
      }
    }
  }

  return portfolio.slice(0, maxSize);
}

function calculateRiskBasedAllocations(portfolio) {
  // Risk rule: 1% per trade / 7.5% stop = 13.3% max position
  const maxPositionSize = 0.133;
  const stopLossPercent = 7.5;

  const totalScore = portfolio.reduce((sum, s) => sum + (s.composite_score || 0), 0);

  // First pass: Calculate raw position sizes based on scores
  let rawAllocations = portfolio.map((stock, index) => {
    // Score-weighted sizing
    const scoreWeight = (stock.composite_score || 60) / totalScore;
    let positionSize = Math.min(maxPositionSize, scoreWeight * 1.5);

    // Minimum 5% for top 12
    if (positionSize < 0.05 && index < 12) {
      positionSize = 0.05;
    }

    return {
      stock: stock,
      index: index,
      positionSize: positionSize
    };
  });

  // Second pass: Normalize so they sum to 100%
  const totalAllocation = rawAllocations.reduce((sum, a) => sum + a.positionSize, 0);
  const normalizationFactor = 1.0 / totalAllocation; // Scale down to sum to 1.0

  const allocations = rawAllocations.map((allocation) => {
    const normalizedSize = allocation.positionSize * normalizationFactor;
    const riskAmount = normalizedSize * (stopLossPercent / 100);

    return {
      symbol: allocation.stock.symbol,
      company: allocation.stock.company_name,
      sector: allocation.stock.sector || 'Other',
      score: Math.round(allocation.stock.composite_score),
      position: parseFloat((normalizedSize * 100).toFixed(2)),
      stopLoss: stopLossPercent,
      riskBps: Math.round(riskAmount * 10000),
      price: allocation.stock.current_price,
      quality: allocation.stock.quality_score,
      momentum: allocation.stock.momentum_score
    };
  });

  return allocations;
}

function generateTradeRecommendations(allocations) {
  return allocations.map((a, idx) => {
    const entry = a.price;
    const stop = entry * (1 - a.stopLoss / 100);
    const target1 = entry * (1 + a.stopLoss / 100);  // 1:1 risk/reward
    const target2 = entry * (1 + (a.stopLoss * 2) / 100); // 2:1 risk/reward

    return {
      rank: idx + 1,
      symbol: a.symbol,
      position: a.position + '%',
      entry: parseFloat(entry.toFixed(2)),
      stop: parseFloat(stop.toFixed(2)),
      target1: parseFloat(target1.toFixed(2)),
      target2: parseFloat(target2.toFixed(2)),
      risk: a.riskBps + 'bps (' + a.position + '% x 7.5%)',
      score: a.score
    };
  });
}

function calculatePortfolioAnalysis(portfolio, allocations) {
  // Calculate portfolio volatility based on component volatilities and correlations
  // For simplicity, estimate portfolio volatility as weighted average of component volatilities
  // In production, would use actual correlation matrix

  const avgStability = portfolio.reduce((sum, s) => sum + (s.stability_score || 50), 0) / portfolio.length;
  const avgMomentum = portfolio.reduce((sum, s) => sum + (s.momentum_score || 50), 0) / portfolio.length;

  // Estimate portfolio volatility (inverse of stability, adjusted by momentum)
  const estimatedVolatility = (100 - avgStability) * (1 + (avgMomentum - 50) / 100);

  // Calculate expected returns based on composite scores (conservative estimate)
  const avgScore = portfolio.reduce((sum, s) => sum + (s.composite_score || 50), 0) / portfolio.length;
  const expectedReturn = (avgScore / 100) * 0.15; // Scale to 15% max annual return

  // Risk-free rate assumption (10-year Treasury)
  const riskFreeRate = 0.04; // 4% current environment

  // Calculate Sharpe ratio
  const expectedSharpeRatio = (expectedReturn - riskFreeRate) / (estimatedVolatility / 100);

  // Diversification score (1-100): Based on sector and factor diversification
  const sectors = new Set(portfolio.map(s => s.sector));
  const factorVariance = calculateFactorVariance(portfolio);
  const diversificationScore = Math.min(100, (sectors.size / 6) * 50 + factorVariance * 50);

  // Correlation risk assessment
  const correlationRisk = estimateCorrelationRisk(portfolio);

  return {
    expectedReturn: expectedReturn * 100,
    expectedVolatility: estimatedVolatility,
    expectedSharpeRatio: Math.max(0, expectedSharpeRatio),
    portfolioVolatility: estimatedVolatility,
    diversificationScore: diversificationScore,
    correlationRisk: correlationRisk,
    numSectors: sectors.size,
    riskFreeRate: riskFreeRate * 100
  };
}

function calculateFactorVariance(portfolio) {
  // Calculate variance across quality, growth, stability, value, momentum
  const factors = ['quality_score', 'growth_score', 'stability_score', 'value_score', 'momentum_score'];

  const factorAverages = factors.map(factor => {
    const avg = portfolio.reduce((sum, s) => sum + (s[factor] || 50), 0) / portfolio.length;
    return avg;
  });

  const variance = factorAverages.reduce((sum, avg) => {
    const diff = avg - 50; // Centered at 50
    return sum + (diff * diff);
  }, 0) / factors.length;

  // Return normalized variance (0-1 scale)
  return Math.min(1, Math.sqrt(variance) / 50);
}

function estimateCorrelationRisk(portfolio) {
  // Estimate correlation risk based on sector and industry concentration
  const sectors = {};
  portfolio.forEach(s => {
    sectors[s.sector] = (sectors[s.sector] || 0) + 1;
  });

  // Calculate Herfindahl index for sector concentration
  const sectorWeights = Object.values(sectors).map(count => count / portfolio.length);
  const herfindahl = sectorWeights.reduce((sum, w) => sum + (w * w), 0);

  // Risk assessment: High Herfindahl = high correlation risk
  if (herfindahl > 0.15) return 'HIGH - Some sector concentration exists';
  if (herfindahl > 0.10) return 'MODERATE - Diversification could improve';
  return 'LOW - Well-diversified across sectors';
}

function generatePerformanceAttribution(portfolio) {
  // Break down each stock's performance potential by factor
  return portfolio.map(stock => ({
    symbol: stock.symbol,
    company: stock.company_name,
    compositeScore: Math.round(stock.composite_score),
    factors: {
      quality: {
        score: Math.round(stock.quality_score || 0),
        contribution: 'Fundamental strength'
      },
      growth: {
        score: Math.round(stock.growth_score || 0),
        contribution: 'Earnings/revenue growth potential'
      },
      stability: {
        score: Math.round(stock.stability_score || 0),
        contribution: 'Price stability/downside protection'
      },
      value: {
        score: Math.round(stock.value_score || 0),
        contribution: 'Valuation attractiveness'
      },
      momentum: {
        score: Math.round(stock.momentum_score || 0),
        contribution: 'Technical momentum'
      }
    },
    primaryDriver: identifyPrimaryDriver(stock),
    risks: identifyStockRisks(stock)
  }));
}

function identifyPrimaryDriver(stock) {
  const scores = {
    quality: stock.quality_score,
    growth: stock.growth_score,
    stability: stock.stability_score,
    value: stock.value_score,
    momentum: stock.momentum_score
  };

  const highest = Object.entries(scores).reduce((prev, current) =>
    (prev[1] || 0) > (current[1] || 0) ? prev : current
  );

  const driverMap = {
    quality: 'Fundamental Quality',
    growth: 'Growth Potential',
    stability: 'Defensive/Stable',
    value: 'Value Play',
    momentum: 'Momentum/Technical'
  };

  return driverMap[highest[0]];
}

function identifyStockRisks(stock) {
  const risks = [];

  if ((stock.quality_score || 0) < 40) risks.push('Low fundamental quality');
  if ((stock.stability_score || 0) < 40) risks.push('High volatility risk');
  if ((stock.growth_score || 0) < 30) risks.push('Limited growth prospects');
  if ((stock.value_score || 0) < 30) risks.push('Expensive valuation');
  if ((stock.momentum_score || 0) < 30) risks.push('Weak technical momentum');

  return risks.length > 0 ? risks : ['No major risk factors identified'];
}

module.exports = {
  generateSwingTradingPortfolio,
  selectDiversifiedPortfolio,
  calculateRiskBasedAllocations,
  generateTradeRecommendations,
  calculatePortfolioAnalysis,
  generatePerformanceAttribution
};

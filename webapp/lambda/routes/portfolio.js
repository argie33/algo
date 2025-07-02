const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

// Portfolio analytics endpoint for advanced metrics
router.get('/analytics/:userId', async (req, res) => {
  const { userId } = req.params;
  const { timeframe = '1y' } = req.query;
  
  console.log(`Portfolio analytics endpoint called for user: ${userId}, timeframe: ${timeframe}`);
  
  try {
    // Get portfolio holdings
    const holdingsQuery = `
      SELECT 
        symbol,
        quantity,
        market_value,
        cost_basis,
        pnl,
        pnl_percent,
        weight,
        sector,
        last_updated
      FROM portfolio_holdings
      WHERE user_id = $1
      ORDER BY market_value DESC
    `;
    
    const holdingsResult = await query(holdingsQuery, [userId]);
    const holdings = holdingsResult.rows;
    
    // Get portfolio performance history
    const performanceQuery = `
      SELECT 
        date,
        total_value,
        daily_pnl,
        daily_pnl_percent,
        total_pnl,
        total_pnl_percent,
        benchmark_return,
        alpha,
        beta,
        sharpe_ratio,
        max_drawdown,
        volatility
      FROM portfolio_performance
      WHERE user_id = $1
      AND date >= NOW() - INTERVAL $2
      ORDER BY date DESC
    `;
    
    const timeframeMap = {
      '1w': '7 days',
      '1m': '30 days',
      '3m': '90 days',
      '6m': '180 days',
      '1y': '365 days',
      '2y': '730 days'
    };
    
    const performanceResult = await query(performanceQuery, [userId, timeframeMap[timeframe] || '365 days']);
    const performance = performanceResult.rows;
    
    // Calculate advanced analytics
    const analytics = calculateAdvancedAnalytics(holdings, performance);
    
    res.json({
      success: true,
      data: {
        holdings: holdings,
        performance: performance,
        analytics: analytics,
        summary: {
          totalValue: holdings.reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0),
          totalPnL: holdings.reduce((sum, h) => sum + parseFloat(h.pnl || 0), 0),
          numPositions: holdings.length,
          topSector: getTopSector(holdings),
          concentration: calculateConcentration(holdings),
          riskScore: analytics.riskScore
        }
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error fetching portfolio analytics:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch portfolio analytics',
      details: error.message
    });
  }
});

// Portfolio risk analysis endpoint
router.get('/risk-analysis/:userId', async (req, res) => {
  const { userId } = req.params;
  
  console.log(`Portfolio risk analysis endpoint called for user: ${userId}`);
  
  try {
    // Get current holdings for risk analysis
    const holdingsQuery = `
      SELECT 
        symbol,
        quantity,
        market_value,
        weight,
        sector,
        beta,
        volatility
      FROM portfolio_holdings
      WHERE user_id = $1
      ORDER BY market_value DESC
    `;
    
    const holdingsResult = await query(holdingsQuery, [userId]);
    const holdings = holdingsResult.rows;
    
    // Calculate risk metrics
    const riskAnalysis = calculateRiskMetrics(holdings);
    
    res.json({
      success: true,
      data: {
        portfolioBeta: riskAnalysis.portfolioBeta,
        portfolioVolatility: riskAnalysis.portfolioVolatility,
        var95: riskAnalysis.var95,
        var99: riskAnalysis.var99,
        sectorConcentration: riskAnalysis.sectorConcentration,
        positionConcentration: riskAnalysis.positionConcentration,
        correlationMatrix: riskAnalysis.correlationMatrix,
        riskScore: riskAnalysis.riskScore,
        recommendations: generateRiskRecommendations(riskAnalysis)
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error performing portfolio risk analysis:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to perform portfolio risk analysis',
      details: error.message
    });
  }
});

// Portfolio optimization suggestions
router.get('/optimization/:userId', async (req, res) => {
  const { userId } = req.params;
  
  console.log(`Portfolio optimization endpoint called for user: ${userId}`);
  
  try {
    // Get current portfolio
    const holdingsQuery = `
      SELECT 
        symbol,
        quantity,
        market_value,
        weight,
        sector,
        expected_return,
        volatility,
        beta
      FROM portfolio_holdings
      WHERE user_id = $1
    `;
    
    const holdingsResult = await query(holdingsQuery, [userId]);
    const holdings = holdingsResult.rows;
    
    // Generate optimization suggestions
    const optimizations = generateOptimizationSuggestions(holdings);
    
    res.json({
      success: true,
      data: {
        currentAllocation: calculateCurrentAllocation(holdings),
        suggestedAllocation: optimizations.suggestedAllocation,
        rebalanceNeeded: optimizations.rebalanceNeeded,
        expectedImprovement: optimizations.expectedImprovement,
        actions: optimizations.actions,
        riskReduction: optimizations.riskReduction,
        diversificationScore: optimizations.diversificationScore
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error generating portfolio optimization:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to generate portfolio optimization',
      details: error.message
    });
  }
});

// Helper functions for calculations
function calculateAdvancedAnalytics(holdings, performance) {
  const totalValue = holdings.reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0);
  
  // Calculate Sharpe ratio
  const returns = performance.slice(0, 252).map(p => parseFloat(p.daily_pnl_percent || 0));
  const avgReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length;
  const volatility = Math.sqrt(returns.reduce((sum, r) => sum + Math.pow(r - avgReturn, 2), 0) / returns.length);
  const sharpeRatio = volatility > 0 ? (avgReturn * 252) / (volatility * Math.sqrt(252)) : 0;
  
  // Calculate max drawdown
  let maxDrawdown = 0;
  let peak = 0;
  performance.forEach(p => {
    const value = parseFloat(p.total_value || 0);
    if (value > peak) peak = value;
    const drawdown = (peak - value) / peak;
    if (drawdown > maxDrawdown) maxDrawdown = drawdown;
  });
  
  // Calculate alpha and beta
  const benchmarkReturns = performance.slice(0, 252).map(p => parseFloat(p.benchmark_return || 0));
  const { alpha, beta } = calculateAlphaBeta(returns, benchmarkReturns);
  
  // Risk score (1-10, 10 being highest risk)
  const riskScore = Math.min(10, Math.max(1, 
    (volatility * 100 * 2) + 
    (maxDrawdown * 100 * 0.5) + 
    (Math.abs(beta - 1) * 2)
  ));
  
  return {
    sharpeRatio: sharpeRatio,
    maxDrawdown: maxDrawdown,
    alpha: alpha,
    beta: beta,
    volatility: volatility,
    riskScore: Math.round(riskScore * 10) / 10,
    calmarRatio: avgReturn * 252 / (maxDrawdown || 0.01),
    sortinoRatio: calculateSortinoRatio(returns),
    informationRatio: calculateInformationRatio(returns, benchmarkReturns)
  };
}

function calculateRiskMetrics(holdings) {
  const totalValue = holdings.reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0);
  
  // Portfolio beta (weighted average)
  const portfolioBeta = holdings.reduce((sum, h) => {
    const weight = parseFloat(h.market_value || 0) / totalValue;
    const beta = parseFloat(h.beta || 1);
    return sum + (weight * beta);
  }, 0);
  
  // Portfolio volatility (simplified)
  const portfolioVolatility = holdings.reduce((sum, h) => {
    const weight = parseFloat(h.market_value || 0) / totalValue;
    const volatility = parseFloat(h.volatility || 0.2);
    return sum + (weight * volatility);
  }, 0);
  
  // VaR calculations (simplified)
  const var95 = portfolioVolatility * 1.645; // 95% confidence
  const var99 = portfolioVolatility * 2.326; // 99% confidence
  
  // Sector concentration
  const sectorMap = {};
  holdings.forEach(h => {
    const sector = h.sector || 'Other';
    const value = parseFloat(h.market_value || 0);
    sectorMap[sector] = (sectorMap[sector] || 0) + value;
  });
  
  const sectorConcentration = Object.values(sectorMap).map(value => value / totalValue);
  
  // Position concentration (top 10 positions)
  const sortedHoldings = holdings.sort((a, b) => parseFloat(b.market_value || 0) - parseFloat(a.market_value || 0));
  const top10Concentration = sortedHoldings.slice(0, 10).reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0) / totalValue;
  
  return {
    portfolioBeta,
    portfolioVolatility,
    var95,
    var99,
    sectorConcentration,
    positionConcentration: top10Concentration,
    riskScore: Math.round((portfolioBeta + portfolioVolatility * 5 + top10Concentration * 2) * 10) / 10
  };
}

function generateOptimizationSuggestions(holdings) {
  const totalValue = holdings.reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0);
  
  // Current allocation
  const currentAllocation = holdings.map(h => ({
    symbol: h.symbol,
    weight: parseFloat(h.market_value || 0) / totalValue,
    sector: h.sector
  }));
  
  // Simple optimization suggestions
  const actions = [];
  const overweightThreshold = 0.15; // 15%
  const underweightThreshold = 0.02; // 2%
  
  currentAllocation.forEach(position => {
    if (position.weight > overweightThreshold) {
      actions.push({
        type: 'reduce',
        symbol: position.symbol,
        currentWeight: position.weight,
        suggestedWeight: overweightThreshold,
        reason: 'Overweight position - reduce concentration risk'
      });
    } else if (position.weight < underweightThreshold && position.weight > 0) {
      actions.push({
        type: 'consider_exit',
        symbol: position.symbol,
        currentWeight: position.weight,
        reason: 'Very small position - consider consolidating'
      });
    }
  });
  
  return {
    suggestedAllocation: currentAllocation, // Simplified
    rebalanceNeeded: actions.length > 0,
    actions: actions,
    expectedImprovement: {
      riskReduction: '5-10%',
      expectedReturn: '+0.5-1.0%'
    },
    diversificationScore: Math.min(10, holdings.length / 2) // Simple score
  };
}

function calculateAlphaBeta(returns, benchmarkReturns) {
  if (returns.length !== benchmarkReturns.length || returns.length === 0) {
    return { alpha: 0, beta: 1 };
  }
  
  const avgReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length;
  const avgBenchmark = benchmarkReturns.reduce((sum, r) => sum + r, 0) / benchmarkReturns.length;
  
  let covariance = 0;
  let benchmarkVariance = 0;
  
  for (let i = 0; i < returns.length; i++) {
    covariance += (returns[i] - avgReturn) * (benchmarkReturns[i] - avgBenchmark);
    benchmarkVariance += Math.pow(benchmarkReturns[i] - avgBenchmark, 2);
  }
  
  const beta = benchmarkVariance > 0 ? covariance / benchmarkVariance : 1;
  const alpha = avgReturn - (beta * avgBenchmark);
  
  return { alpha, beta };
}

function calculateSortinoRatio(returns) {
  const avgReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length;
  const downside = returns.filter(r => r < 0);
  
  if (downside.length === 0) return 0;
  
  const downsideDeviation = Math.sqrt(downside.reduce((sum, r) => sum + Math.pow(r, 2), 0) / downside.length);
  return downsideDeviation > 0 ? (avgReturn * 252) / (downsideDeviation * Math.sqrt(252)) : 0;
}

function calculateInformationRatio(returns, benchmarkReturns) {
  if (returns.length !== benchmarkReturns.length) return 0;
  
  const excessReturns = returns.map((r, i) => r - benchmarkReturns[i]);
  const avgExcess = excessReturns.reduce((sum, r) => sum + r, 0) / excessReturns.length;
  const trackingError = Math.sqrt(excessReturns.reduce((sum, r) => sum + Math.pow(r - avgExcess, 2), 0) / excessReturns.length);
  
  return trackingError > 0 ? (avgExcess * 252) / (trackingError * Math.sqrt(252)) : 0;
}

function getTopSector(holdings) {
  const sectorMap = {};
  holdings.forEach(h => {
    const sector = h.sector || 'Other';
    const value = parseFloat(h.market_value || 0);
    sectorMap[sector] = (sectorMap[sector] || 0) + value;
  });
  
  return Object.entries(sectorMap).reduce((top, [sector, value]) => 
    value > top.value ? { sector, value } : top, 
    { sector: 'None', value: 0 }
  ).sector;
}

function calculateConcentration(holdings) {
  const totalValue = holdings.reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0);
  const top5Value = holdings
    .sort((a, b) => parseFloat(b.market_value || 0) - parseFloat(a.market_value || 0))
    .slice(0, 5)
    .reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0);
  
  return totalValue > 0 ? top5Value / totalValue : 0;
}

function calculateCurrentAllocation(holdings) {
  const totalValue = holdings.reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0);
  return holdings.map(h => ({
    symbol: h.symbol,
    weight: parseFloat(h.market_value || 0) / totalValue,
    sector: h.sector
  }));
}

function generateRiskRecommendations(riskAnalysis) {
  const recommendations = [];
  
  if (riskAnalysis.portfolioBeta > 1.3) {
    recommendations.push({
      type: 'high_beta',
      message: 'Portfolio has high beta - consider adding defensive positions',
      priority: 'medium'
    });
  }
  
  if (riskAnalysis.positionConcentration > 0.5) {
    recommendations.push({
      type: 'concentration',
      message: 'High concentration in top positions - consider diversifying',
      priority: 'high'
    });
  }
  
  if (riskAnalysis.portfolioVolatility > 0.25) {
    recommendations.push({
      type: 'volatility',
      message: 'High portfolio volatility - consider adding stable assets',
      priority: 'medium'
    });
  }
  
  return recommendations;
}

module.exports = router;
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

    return {
      success: true,
      portfolio: portfolio,
      allocations: allocations,
      recommendations: recommendations,
      summary: {
        stockCount: portfolio.length,
        totalAllocation: '100%',
        riskMetrics: {
          totalPortfolioRisk: '1% per position',
          maxPosition: '13.3%',
          defaultStopLoss: '7.5%',
          avgRiskReward: '1:1 to 2:1'
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

  const allocations = portfolio.map((stock, index) => {
    // Score-weighted sizing
    const scoreWeight = (stock.composite_score || 60) / totalScore;
    let positionSize = Math.min(maxPositionSize, scoreWeight * 1.5);

    // Minimum 5% for top 12
    if (positionSize < 0.05 && index < 12) {
      positionSize = 0.05;
    }

    const riskAmount = positionSize * (stopLossPercent / 100);

    return {
      symbol: stock.symbol,
      company: stock.company_name,
      sector: stock.sector || 'Other',
      score: Math.round(stock.composite_score),
      position: parseFloat((positionSize * 100).toFixed(2)),
      stopLoss: stopLossPercent,
      riskBps: Math.round(riskAmount * 10000),
      price: stock.current_price,
      quality: stock.quality_score,
      momentum: stock.momentum_score
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

module.exports = {
  generateSwingTradingPortfolio,
  selectDiversifiedPortfolio,
  calculateRiskBasedAllocations,
  generateTradeRecommendations
};
